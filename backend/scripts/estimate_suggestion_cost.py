"""액션 카드 서술(호출 B, suggest-v4) 한 번의 예상 비용 상한을 계산한다. 읽기 전용이고 OpenAI를 부르지 않는다. DB에 쓰지 않는다.

backend 폴더에서 실행한다.
  python scripts/estimate_suggestion_cost.py                 # 제품군 x 회차 모든 조합
  python scripts/estimate_suggestion_cost.py --family-id 2 --round-label 2026-Q1

- 스냅샷을 메모리에서만 계산하고(저장하지 않음), 실제 프롬프트 글자 수로 estimate_suggestion_cost를 부른다.
- 계수는 모두 가정이다(app/llm/cost.py SuggestionCalibration). suggest-v4(카드 3개 x (우선순위 문장 120자 + 산출물 200자))는 아직 실제로 불러 본 적이 없다.
- 단가와 한도는 backend/.env의 OPENAI_PRICE_*, SUGGESTION_COST_LIMIT_USD를 쓴다(없으면 기본 한도 0.5). 숫자만 출력한다.
"""

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

from app.config import VOC_SMALL_SAMPLE_THRESHOLD, get_settings  # noqa: E402
from app.db import make_engine  # noqa: E402
from app.llm.cost import Prices, estimate_suggestion_cost  # noqa: E402
from app.models import ProductFamily, Round  # noqa: E402
from app.services.snapshot import compute_snapshot  # noqa: E402
from app.services.action_cards import select_areas  # noqa: E402
from app.services.suggestion_step import option_labels, prompts_for_areas  # noqa: E402

logging.disable(logging.CRITICAL)
PREFIX = "[파일럿-임시]"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--family-id", type=int)
    parser.add_argument("--round-label")
    args = parser.parse_args()

    settings = get_settings()
    if settings.price_input_per_m is None or settings.price_output_per_m is None:
        print("실패: 단가가 설정되지 않았습니다. backend/.env의 OPENAI_PRICE_* 항목을 채워 주세요.")
        return 1
    prices = Prices(settings.price_input_per_m, settings.price_output_per_m)
    limit = settings.suggestion_cost_limit_usd
    engine = make_engine()
    total_one = total_upper = 0.0
    count = 0
    with Session(engine) as session:
        print(f"대상 DB: {engine.dialect.name} (읽기만, 저장하지 않음, OpenAI 호출 없음) | 한도 ${limit:.2f}")
        for family in session.query(ProductFamily).order_by(ProductFamily.family_id):
            for round_row in session.query(Round).order_by(Round.round_id):
                if round_row.label.startswith(PREFIX):
                    continue
                if (args.family_id and family.family_id != args.family_id) or (args.round_label and round_row.label != args.round_label):
                    continue
                table, evidence = compute_snapshot(
                    session, family, round_row, weight_floor=settings.ad_weight_floor, small_sample_threshold=VOC_SMALL_SAMPLE_THRESHOLD
                )
                areas = select_areas(table, evidence, option_labels(session, round_row.round_id))
                system_prompt, user_prompt = prompts_for_areas(areas)
                estimate = estimate_suggestion_cost(len(system_prompt), len(user_prompt), prices)
                total_one += estimate.one_pass_usd
                total_upper += estimate.upper_usd
                count += 1
                print(
                    f"제품군 {family.family_id} {round_row.label}: 영역 {len(areas)}개, 프롬프트 글자 수 {len(system_prompt)}(시스템) + {len(user_prompt)}(영역)"
                    f" | 입력 토큰 상한 {estimate.input_tokens:,}, 출력 토큰 상한 {estimate.output_tokens:,}"
                    f" | 한 번 ${estimate.one_pass_usd:.4f}, 재시도 배수 {3} 적용 ${estimate.upper_usd:.4f}"
                    f" | 한도 {'넘지 않음' if estimate.upper_usd <= limit else '넘음'}"
                )
    print(f"{count}개 조합 합계: 한 번씩 ${total_one:.4f}, 상한 합 ${total_upper:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
