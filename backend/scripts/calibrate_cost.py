"""실제 실행 기록으로 비용 계수의 보정 값을 제안한다. DB에서 읽기만 한다. 제안은 자동으로 반영하지 않는다.

backend 폴더에서 실행한다:
  python scripts/calibrate_cost.py --run-id 12

- llm_call_log의 호출별 토큰 수와 ad_judgement로 복원한 묶음의 글자 수(길이만)를 짝지어 계산한다.
- 재시도가 섞인 실행은 묶음을 복원할 수 없어 쓰지 않는다(호출 수가 묶음 수와 같고 모두 1번째 시도의 성공이어야 한다).
- 결과 숫자를 보고 사용자가 OK 한 뒤에 app/llm/cost.py의 CALIBRATION 한 곳만 고친다.
- 리뷰 본문, 제목, 작성자는 읽지도 출력하지도 않는다. OpenAI를 호출하지 않는다.
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.llm.cost import CALIBRATION, CallSample, suggest_calibration  # noqa: E402
from app.models import AdJudgement, LlmCallLog  # noqa: E402
from app.services.ad_cost import char_counts_to_send  # noqa: E402
from app.services.ad_judgement import BATCH_SIZE  # noqa: E402


def collect_samples(session: Session, run_id: int, batch_size: int = BATCH_SIZE) -> list[CallSample]:
    """한 실행의 호출별 (항목 수, 글자 수 합계, 실제 토큰 수)를 만든다. 복원할 수 없으면 ValueError."""
    sent_ids = list(
        session.scalars(
            select(AdJudgement.review_id)
            .where(AdJudgement.run_id == run_id, AdJudgement.status.in_(("ok", "failed")))
            .order_by(AdJudgement.review_id)
        )
    )
    calls = list(session.scalars(select(LlmCallLog).where(LlmCallLog.run_id == run_id).order_by(LlmCallLog.call_id)))
    chunks = [sent_ids[start : start + batch_size] for start in range(0, len(sent_ids), batch_size)]
    if not chunks or len(calls) != len(chunks):
        raise ValueError("호출 수가 묶음 수와 달라 복원할 수 없습니다(재시도가 섞였거나 실행 기록이 없습니다).")
    samples = []
    for chunk, call in zip(chunks, calls):
        if call.attempt_no != 1 or call.status != "ok" or call.item_count != len(chunk):
            raise ValueError("재시도가 섞인 호출이 있어 복원할 수 없습니다.")
        if call.input_tokens is None or call.output_tokens is None:
            raise ValueError("토큰 수가 없는 호출이 있어 쓸 수 없습니다.")
        chars = sum(char_counts_to_send(session, chunk))
        samples.append(CallSample(len(chunk), chars, call.input_tokens, call.output_tokens))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="실행 기록으로 비용 계수의 보정 값을 제안한다.")
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args()
    try:
        engine = make_engine()
        with Session(engine) as session:
            samples = collect_samples(session, args.run_id)
    except ValueError as error:
        print(f"실패: {error}")
        return 1
    except Exception as error:  # 오류 메시지에 접속 정보가 들어갈 수 있어 종류만 출력한다.
        print(f"실패: DB에서 읽지 못했습니다 ({type(error).__name__}).")
        return 1

    suggestion = suggest_calibration(samples)
    print(f"== 대상 DB: {engine.dialect.name} (읽기만 합니다), 실행 {args.run_id}, 표본 호출 {suggestion.samples_used}회")
    print(f"tokens_per_char  현재 {CALIBRATION.tokens_per_char} -> 제안 {suggestion.tokens_per_char}")
    print(f"output_tokens_per_item  현재 {CALIBRATION.output_tokens_per_item} -> 제안 {suggestion.output_tokens_per_item}")
    print("고정 입력과 항목 오버헤드는 한 표본으로는 가를 수 없어 현재 값을 그대로 씁니다.")
    print("자동으로 반영하지 않습니다. 확인한 뒤 app/llm/cost.py의 CALIBRATION 한 곳만 고칩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
