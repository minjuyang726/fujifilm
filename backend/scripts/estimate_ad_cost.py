"""광고성 판정을 돌리기 전에 예상 비용 상한을 계산해 출력한다. DB에서 글자 수만 읽고 아무것도 쓰지 않는다.

backend 폴더에서 실행한다:
  python scripts/estimate_ad_cost.py                       # 파일럿 표본(database/data/pilot_sample_ids.json)
  python scripts/estimate_ad_cost.py --ids 1 2 3           # review_id를 직접 지정

- 단가는 backend/.env의 OPENAI_PRICE_INPUT_PER_M, OPENAI_PRICE_OUTPUT_PER_M, 한도는 AD_JUDGEMENT_COST_LIMIT_USD(기본 0.5)다.
- 출력은 건수, 토큰 수, 비용 숫자뿐이다. 리뷰 본문, 제목, 작성자는 읽지도 출력하지도 않는다.
- 이 스크립트는 OpenAI를 호출하지 않는다.
"""

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import make_engine  # noqa: E402
from app.llm.cost import CALIBRATION, Prices, estimate_ad_cost  # noqa: E402
from app.services.ad_cost import char_counts_to_send  # noqa: E402
from app.services.ad_judgement import BATCH_SIZE  # noqa: E402

DEFAULT_IDS_FILE = BACKEND_DIR.parent / "database" / "data" / "pilot_sample_ids.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="광고성 판정의 예상 비용 상한을 계산한다.")
    parser.add_argument("--ids", type=int, nargs="+", help="review_id 목록. 없으면 표본 파일을 읽는다.")
    parser.add_argument("--ids-file", type=Path, default=DEFAULT_IDS_FILE)
    args = parser.parse_args()

    settings = get_settings()
    if settings.price_input_per_m is None or settings.price_output_per_m is None:
        print("실패: 단가가 설정되지 않았습니다. backend/.env의 단가 항목을 채워 주세요.")
        return 1
    prices = Prices(settings.price_input_per_m, settings.price_output_per_m)

    if args.ids:
        review_ids = sorted(set(args.ids))
    else:
        try:
            review_ids = sorted(set(json.loads(args.ids_file.read_text(encoding="utf-8"))["review_ids"]))
        except (OSError, ValueError, KeyError):
            print("실패: 표본 파일을 읽지 못했습니다. --ids로 review_id를 직접 주거나 파일 경로를 확인해 주세요.")
            return 1

    try:
        engine = make_engine()
        with Session(engine) as session:
            char_counts = char_counts_to_send(session, review_ids)
    except Exception as error:  # 오류 메시지에 접속 정보가 들어갈 수 있어 종류만 출력한다.
        print(f"실패: DB에서 읽지 못했습니다 ({type(error).__name__}).")
        return 1

    estimate = estimate_ad_cost(char_counts, BATCH_SIZE, prices)
    limit = settings.ad_judgement_cost_limit_usd
    print(f"== 대상 DB: {engine.dialect.name} (읽기만 합니다, OpenAI 호출 없음)")
    print(f"지정한 review_id {len(review_ids)}건 중 보낼 글 {estimate.items}건, 호출 {estimate.calls}회 (묶음 {BATCH_SIZE}건)")
    if char_counts:
        print(f"글자 수(제목+본문): 최소 {min(char_counts)}, 최대 {max(char_counts)}, 평균 {sum(char_counts) / len(char_counts):.1f}")
    print(f"입력 토큰 상한 {estimate.input_tokens:,}, 출력 토큰 상한 {estimate.output_tokens:,}")
    print(f"재시도 없이 한 번: ${estimate.one_pass_usd:.4f}")
    print(f"예상 비용 상한(재시도 배수 {CALIBRATION.retry_multiplier}): ${estimate.upper_usd:.4f}  (참고: 항목별 합계 기준 ${estimate.sum_based_upper_usd:.4f})")
    print(f"한도 ${limit:.2f}: {'넘음 - 호출하지 않습니다' if estimate.upper_usd > limit else '넘지 않음'}")
    print("계수는 가정이 섞여 있습니다(app/llm/cost.py CALIBRATION).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
