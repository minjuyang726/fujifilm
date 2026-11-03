"""step action-suggestions: 스냅샷의 표로 액션 제안 문장을 서술하고(호출 B), 문장별로 검증해 저장한다.

- LLM은 코드가 계산한 표만 받고 문장과 row_ids만 낸다. 근거 ID는 코드가 스냅샷의 허용 목록에서 붙인다(SP-3).
- 문장별로 검증해 통과한 문장만 쓴다(suggestion_validators). 통과한 문장이 0개이거나 스키마가 깨지면 전체를 다시 요청한다(최대 2회).
- 일시 오류(시간 초과, 429, 5xx)는 대기 시간을 늘려 가며 최대 3회 다시 보낸다(1, 2, 4초, 가정).
- 통과한 문장이 하나도 없으면 실행은 failed다. 있으면 report 행 하나와 action_suggestion 행을 저장한다(실행마다 쌓는다, SQ-8).
- 리뷰 본문, 키, LLM 요청·응답 원문은 로그, 실행 기록, llm_call_log 어디에도 남기지 않는다.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.llm.client import LLMClient, PermanentLLMError, TransientLLMError
from app.llm.cost import CostGuard
from app.llm.output_schemas.suggestion import SCHEMA_NAME, SUGGESTION_SCHEMA
from app.llm.prompts.suggestion import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.llm.suggestion_validators import FilterResult, filter_suggestions, parse_suggestions
from app.models import ActionSuggestion, AnalysisSnapshot, LlmCallLog, PipelineRun, ProductFamily, Report, Round

logger = logging.getLogger(__name__)

STEP_NAME = "action-suggestions"
CALL_TYPE = "B"
MAX_VALIDATION_RETRIES = 2  # 통과한 문장이 0개이거나 스키마가 깨졌을 때 전체 재요청 (결정 2026-11-03)
MAX_TRANSIENT_RETRIES = 3  # 일시 오류 재시도 (SQ-9 가정)
BACKOFF_SECONDS = (1, 2, 4)

ERROR_INTERNAL = "INTERNAL_ERROR"
ERROR_COST_LIMIT = "COST_LIMIT"
ERROR_NO_SUGGESTIONS = "NO_SUGGESTIONS"
ERROR_INVALID_OUTPUT = "INVALID_OUTPUT"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def latest_snapshot(session: Session, family_id: int, round_id: int) -> AnalysisSnapshot | None:
    """제품군 x 회차의 가장 최근 스냅샷(computed_at, 같으면 snapshot_id가 큰 쪽)."""
    return session.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.family_id == family_id, AnalysisSnapshot.round_id == round_id)
        .order_by(AnalysisSnapshot.computed_at.desc(), AnalysisSnapshot.snapshot_id.desc())
    ).first()


def build_prompts(snapshot: AnalysisSnapshot) -> tuple[str, str]:
    table = snapshot.table_json
    return SYSTEM_PROMPT, build_user_prompt(table["family"], table["round"], table["rows"])


def run_action_suggestions(
    session: Session,
    *,
    round_row: Round,
    family: ProductFamily,
    snapshot: AnalysisSnapshot,
    client: LLMClient,
    model_name: str,
    cost_guard: CostGuard | None = None,
    sleep: Callable[[float], None] = time.sleep,
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
    snapshot_id = snapshot.snapshot_id
    log_event(logger, logging.INFO, "action_suggestions_start", run_id=run_id, step=STEP_NAME, snapshot_id=snapshot_id)

    try:
        table = snapshot.table_json
        rows_by_id = {row["row_id"]: row for row in table["rows"]}
        allowed = snapshot.allowed_evidence_json
        system_prompt, user_prompt = build_prompts(snapshot)

        counters = {
            "proposed": 0,
            "accepted": 0,
            "dropped_no_evidence": 0,
            "dropped_number_mismatch": 0,
            "dropped_other": 0,
            "attempts": 0,
            "llm_calls": 0,
        }
        final: FilterResult | None = None
        error_code: str | None = None
        stop = False
        call_no = 0

        for attempt in range(1 + MAX_VALIDATION_RETRIES):
            counters["attempts"] = attempt + 1
            # ---- 호출 한 번(일시 오류는 대기 후 다시 보낸다) ----
            result = None
            transient_retries = 0
            while True:
                call_no += 1
                started = time.perf_counter()
                try:
                    result = client.complete_json(
                        model=model_name,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        schema_name=SCHEMA_NAME,
                        json_schema=SUGGESTION_SCHEMA,
                    )
                    problem = None
                except TransientLLMError as error:
                    problem = error.code
                    transient = True
                except PermanentLLMError as error:
                    problem = error.code
                    transient = False
                latency_ms = int((time.perf_counter() - started) * 1000)
                counters["llm_calls"] = call_no
                if problem is None:
                    break
                session.add(
                    LlmCallLog(
                        run_id=run_id, call_type=CALL_TYPE, model_name=model_name, prompt_version=PROMPT_VERSION,
                        attempt_no=call_no, status="api_error", item_count=len(rows_by_id), latency_ms=latency_ms,
                        error_code=problem, input_tokens=None, output_tokens=None, created_at=now(),
                    )
                )
                if not transient or transient_retries >= MAX_TRANSIENT_RETRIES:
                    error_code = problem
                    stop = True
                    break
                log_event(logger, logging.WARNING, "action_suggestions_retry", run_id=run_id, error_code=problem, retry=transient_retries + 1)
                sleep(BACKOFF_SECONDS[min(transient_retries, len(BACKOFF_SECONDS) - 1)])
                transient_retries += 1
            if stop:
                break

            if cost_guard is not None:
                cost_guard.record(result.input_tokens, result.output_tokens)

            # ---- 검증 ----
            parsed = parse_suggestions(result.text)
            filtered = FilterResult()
            if parsed.problem is None:
                filtered = filter_suggestions(parsed.items, rows_by_id, allowed, table["family"], table["round"])
            session.add(
                LlmCallLog(
                    run_id=run_id, call_type=CALL_TYPE, model_name=model_name, prompt_version=PROMPT_VERSION,
                    attempt_no=call_no, status="ok" if filtered.accepted else "invalid_output", item_count=len(rows_by_id),
                    latency_ms=latency_ms, error_code=parsed.problem, input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens, created_at=now(),
                )
            )
            final = filtered
            for key in ("proposed", "accepted", "dropped_no_evidence", "dropped_number_mismatch", "dropped_other"):
                counters[key] = filtered.counters[key]  # 마지막으로 검증한 시도의 건수
            if filtered.accepted:
                break
            error_code = ERROR_INVALID_OUTPUT if parsed.problem else ERROR_NO_SUGGESTIONS
            if cost_guard is not None and cost_guard.exceeded:
                error_code = ERROR_COST_LIMIT
                break

        accepted = final.accepted if final is not None else []
        if accepted:
            report = Report(round_id=round_row.round_id, family_id=family.family_id, run_id=run_id, generated_at=now())
            session.add(report)
            session.flush()
            for order_no, item in enumerate(accepted, start=1):
                session.add(
                    ActionSuggestion(
                        report_id=report.report_id, snapshot_id=snapshot_id, order_no=order_no,
                        sentence=item["sentence"], row_ids=item["row_ids"],
                    )
                )
            status, error_code = "succeeded", None
        else:
            status = "failed"
            error_code = error_code or ERROR_NO_SUGGESTIONS
        run = session.get(PipelineRun, run_id)
        run.status = status
        run.counters = counters
        run.error_code = error_code
        run.finished_at = now()
        session.commit()
        log_event(logger, logging.INFO, "action_suggestions_end", run_id=run_id, step=STEP_NAME, status=status, error_code=error_code, **counters)
        return run
    except Exception as error:  # 오류 메시지에 요청 내용이 들어갈 수 있어 종류만 기록한다.
        session.rollback()
        failed_run = session.get(PipelineRun, run_id)
        failed_run.status = "failed"
        failed_run.error_code = ERROR_INTERNAL
        failed_run.finished_at = now()
        session.commit()
        log_event(logger, logging.ERROR, "action_suggestions_failed", run_id=run_id, step=STEP_NAME, error_type=type(error).__name__)
        return failed_run
