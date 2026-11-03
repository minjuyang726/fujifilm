"""step analysis-snapshot: 제품군 x 회차의 표를 계산해 저장한다. LLM을 쓰지 않는다. 실행마다 새 스냅샷을 쌓는다(SQ-8)."""

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.models import AnalysisSnapshot, PipelineRun, ProductFamily, Round
from app.services.snapshot import compute_snapshot

STEP_NAME = "analysis-snapshot"
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_analysis_snapshot(
    session: Session,
    *,
    family: ProductFamily,
    round_row: Round,
    weight_floor: float,
    small_sample_threshold: int,
    now: Callable[[], datetime] = _utc_now,
) -> PipelineRun:
    run = PipelineRun(
        round_id=round_row.round_id,
        family_id=family.family_id,
        step=STEP_NAME,
        status="running",
        counters={},
        started_at=now(),
    )
    session.add(run)
    session.commit()
    run_id = run.run_id
    log_event(logger, logging.INFO, "analysis_snapshot_start", run_id=run_id, step=STEP_NAME)
    try:
        table, evidence = compute_snapshot(
            session, family, round_row, weight_floor=weight_floor, small_sample_threshold=small_sample_threshold
        )
        session.add(
            AnalysisSnapshot(
                run_id=run_id,
                round_id=round_row.round_id,
                family_id=family.family_id,
                table_json=table,
                allowed_evidence_json=evidence,
                computed_at=now(),
            )
        )
        run = session.get(PipelineRun, run_id)
        run.status = "succeeded"
        run.counters = {
            "rows": len(table["rows"]),
            "survey_rows": sum(1 for r in table["rows"] if r["group"] == "설문"),
            "voc_rows": sum(1 for r in table["rows"] if r["group"] == "VOC"),
            "evidence_ids": sum(len(v["ids"]) for v in evidence.values()),
        }
        run.finished_at = now()
        session.commit()
    except Exception:
        session.rollback()
        run = session.get(PipelineRun, run_id)
        run.status = "failed"
        run.error_code = "SNAPSHOT_FAILED"
        run.finished_at = now()
        session.commit()
        log_event(logger, logging.ERROR, "analysis_snapshot_failed", run_id=run_id, step=STEP_NAME, error_code="SNAPSHOT_FAILED")
        raise
    log_event(logger, logging.INFO, "analysis_snapshot_end", run_id=run_id, step=STEP_NAME, status=run.status, **run.counters)
    return run
