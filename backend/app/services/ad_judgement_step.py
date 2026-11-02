"""파이프라인 단계 ad-judgement. 실행 기록(pipeline_run)을 만들고 판정 결과를 저장한다.

- 제목과 본문이 모두 없는 리뷰는 LLM에 보내지 않고 status=skipped로 기록한다(P-5, FR-1.11).
- 한 실행에서 LLM에 보내는 글 수는 max_items로 제한한다. 넘는 글은 기록하지 않고 counters.not_run에 센다.
- 리뷰 본문과 키는 로그, 실행 기록, llm_call_log 어디에도 남기지 않는다.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.client import LLMClient
from app.llm.cost import CostGuard
from app.llm.prompts.ad_judgement import PROMPT_VERSION
from app.models import AdJudgement, LlmCallLog, PipelineRun, Review
from app.services.ad_judgement import BATCH_SIZE, CallRecord, ReviewInput, judge_reviews

logger = logging.getLogger(__name__)

STEP_NAME = "ad-judgement"
CALL_TYPE = "A"
ERROR_INTERNAL = "INTERNAL_ERROR"
ERROR_COST_LIMIT = "COST_LIMIT"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_ad_judgement_step(
    session: Session,
    *,
    round_id: int,
    family_id: int | None,
    client: LLMClient,
    model_name: str,
    max_items: int,
    review_ids: Iterable[int] | None = None,
    batch_size: int = BATCH_SIZE,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _utc_now,
    cost_guard: CostGuard | None = None,
) -> PipelineRun:
    run = PipelineRun(
        round_id=round_id,
        family_id=family_id,
        step=STEP_NAME,
        status="running",
        counters={},
        started_at=now(),
    )
    session.add(run)
    session.commit()
    run_id = run.run_id
    logger.info("ad-judgement 시작 run_id=%s", run_id)

    try:
        rows = session.execute(
            select(Review.review_id, Review.title, Review.review_text).order_by(Review.review_id)
        ).all()
        if review_ids is not None:
            selected = set(review_ids)
            rows = [row for row in rows if row.review_id in selected]

        skipped_ids = [row.review_id for row in rows if row.title is None and row.review_text is None]
        eligible = [
            ReviewInput(row.review_id, row.title, row.review_text)
            for row in rows
            if row.title is not None or row.review_text is not None
        ]
        to_send = eligible[:max_items]
        over_cap = len(eligible) - len(to_send)

        def record_call(record: CallRecord) -> None:
            if cost_guard is not None:
                cost_guard.record(record.input_tokens, record.output_tokens)
            session.add(
                LlmCallLog(
                    run_id=run_id,
                    call_type=CALL_TYPE,
                    model_name=model_name,
                    prompt_version=PROMPT_VERSION,
                    attempt_no=record.attempt_no,
                    status=record.status,
                    item_count=record.item_count,
                    latency_ms=record.latency_ms,
                    error_code=record.error_code,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    created_at=now(),
                )
            )

        report = judge_reviews(
            client,
            model_name,
            to_send,
            batch_size=batch_size,
            sleep=sleep,
            on_call=record_call,
            should_stop=(lambda: cost_guard.exceeded) if cost_guard is not None else (lambda: False),
        )

        judged_at = now()
        for review_id in skipped_ids:
            session.add(
                AdJudgement(review_id=review_id, run_id=run_id, status="skipped", judged_at=judged_at)
            )
        for outcome in report.outcomes:
            session.add(
                AdJudgement(
                    review_id=outcome.review_id,
                    run_id=run_id,
                    ad_probability=outcome.ad_probability,
                    ad_weight=None if outcome.ad_probability is None else 1.0 - outcome.ad_probability,
                    model_name=model_name,
                    prompt_version=PROMPT_VERSION,
                    status=outcome.status,
                    error_code=outcome.error_code,
                    judged_at=judged_at,
                )
            )

        ok = sum(1 for outcome in report.outcomes if outcome.status == "ok")
        failed = sum(1 for outcome in report.outcomes if outcome.status == "failed")
        counters = {
            "eligible": len(eligible),
            "skipped": len(skipped_ids),
            "sent": len(report.outcomes),
            "ok": ok,
            "failed": failed,
            "not_run": over_cap + len(report.not_run),
        }
        if failed == 0:
            status, error_code = "succeeded", None
        else:
            status = "failed" if ok == 0 else "partial"
            error_code = Counter(
                outcome.error_code for outcome in report.outcomes if outcome.status == "failed"
            ).most_common(1)[0][0]

        if report.cost_stopped:
            # 누적 비용이 한도를 넘어 남은 묶음을 보내지 않았다. 성공한 것이 있으면 partial이다.
            status = "partial" if ok > 0 else "failed"
            error_code = ERROR_COST_LIMIT
            logger.warning(
                "ad-judgement 비용 한도 초과로 중단 run_id=%s spent_usd=%.6f limit_usd=%.2f",
                run_id,
                cost_guard.spent_usd if cost_guard is not None else 0.0,
                cost_guard.limit_usd if cost_guard is not None else 0.0,
            )

        run.status = status
        run.counters = counters
        run.error_code = error_code
        run.finished_at = now()
        session.commit()
        logger.info("ad-judgement 끝 run_id=%s status=%s counters=%s", run_id, status, counters)
        return run
    except Exception as error:  # 오류 메시지에 리뷰 본문이나 접속 정보가 들어갈 수 있어 종류만 기록한다.
        session.rollback()
        failed_run = session.get(PipelineRun, run_id)
        failed_run.status = "failed"
        failed_run.error_code = ERROR_INTERNAL
        failed_run.finished_at = now()
        session.commit()
        logger.error("ad-judgement 실패 run_id=%s error=%s", run_id, type(error).__name__)
        return failed_run
