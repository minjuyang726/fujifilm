"""다음 회차 문항 초안(호출 C) 한 번의 예상 비용 상한을 계산한다. 읽기 전용이고 OpenAI를 부르지 않는다. DB에 쓰지 않는다.

backend 폴더에서 실행한다.
  python scripts/estimate_question_cost.py

- 스냅샷과 가설을 메모리에서만 계산하고(저장하지 않음), 실제 프롬프트 글자 수와 가설 수로 estimate_question_cost를 부른다.
- 계수는 모두 가정이다(app/llm/cost.py QuestionCalibration). 호출 C는 아직 실제로 불러 본 적이 없다.
- 단가와 한도는 backend/.env의 OPENAI_PRICE_*, QUESTION_COST_LIMIT_USD를 쓴다(한도가 없으면 기본 0.5). 숫자만 출력한다.
"""

import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import VOC_SMALL_SAMPLE_THRESHOLD, get_settings  # noqa: E402
from app.db import make_engine  # noqa: E402
from app.llm.cost import Prices, estimate_question_cost  # noqa: E402
from app.models import ProductFamily, Round, SurveyQuestion  # noqa: E402
from app.services.question_step import prompts_for, survey_options  # noqa: E402
from app.services.question_forms import decide_form  # noqa: E402
from app.services.hypotheses import find_hypotheses, question_targets  # noqa: E402
from app.services.snapshot import compute_snapshot  # noqa: E402

logging.disable(logging.CRITICAL)
PREFIX = "[파일럿-임시]"


def main() -> int:
    settings = get_settings()
    if settings.price_input_per_m is None or settings.price_output_per_m is None:
        print("실패: 단가가 설정되지 않았습니다. backend/.env의 OPENAI_PRICE_* 항목을 채워 주세요.")
        return 1
    prices = Prices(settings.price_input_per_m, settings.price_output_per_m)
    limit = settings.question_cost_limit_usd
    total_one = total_upper = 0.0
    with Session(make_engine()) as session:
        print(f"대상 DB: {session.get_bind().dialect.name} (읽기만, 저장하지 않음, OpenAI 호출 없음) | 한도 ${limit:.2f}")
        for family in session.query(ProductFamily).order_by(ProductFamily.family_id):
            for round_row in session.query(Round).order_by(Round.round_id):
                if round_row.label.startswith(PREFIX):
                    continue
                table, _ = compute_snapshot(
                    session, family, round_row, weight_floor=settings.ad_weight_floor, small_sample_threshold=VOC_SMALL_SAMPLE_THRESHOLD
                )
                types = dict(session.execute(select(SurveyQuestion.code, SurveyQuestion.type).where(SurveyQuestion.round_id == round_row.round_id)).all())
                options = survey_options(session, round_row.round_id)
                found = []
                for item in question_targets(find_hypotheses(table, types)):  # R1은 호출 C 입력에서 뺀다
                    spec = decide_form(item["related_row_ids"], options)  # 코드가 형식을 정한다
                    if spec is not None:
                        found.append({**item, "form": spec.form})
                system_prompt, user_prompt = prompts_for([{**item, "hypothesis_id": i} for i, item in enumerate(found, start=1)])
                estimate = estimate_question_cost(len(system_prompt), len(user_prompt), prices, len(found))
                total_one += estimate.one_pass_usd
                total_upper += estimate.upper_usd
                print(
                    f"제품군 {family.family_id} {round_row.label}: 문항 대상 가설 {len(found)}개, 프롬프트 글자 수 {len(system_prompt)}(시스템) + {len(user_prompt)}(가설)"
                    f" | 입력 토큰 상한 {estimate.input_tokens:,}, 출력 토큰 상한 {estimate.output_tokens:,}"
                    f" | 한 번 ${estimate.one_pass_usd:.4f}, 재시도 배수 3 적용 ${estimate.upper_usd:.4f}"
                    f" | 한도 {'넘지 않음' if estimate.upper_usd <= limit else '넘음'}"
                )
    print(f"합계: 한 번씩 ${total_one:.4f}, 상한 합 ${total_upper:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
