"""step action-suggestions(suggest-v4 액션 카드): 코드가 정한 개선 영역 3개에 대해 모델이 카드 문장과 산출물만 쓰고, 코드가 검증해 저장한다.

- 영역 선정, 순위, 순위 라벨, 값은 모두 코드가 계산한다(app/services/action_cards.py). 모델 입력에는 area_code, 라벨, 순위 라벨만 있다.
- 모델은 자리표시자({pct}, {rank})가 든 우선순위 문장과 산출물만 쓴다. 코드가 값을 채워 문장 하나로 저장한다.
  저장 형식(기존 action_suggestion 컬럼 그대로): sentence = "합성 설문 기준 '라벨' 영역 — 우선순위 문장 ▸ 산출물(종류): 본문",
  row_ids = q08 해당 보기 행과 q07의 같은 영역 보기 행. 쿠팡 리뷰 카드(코드 템플릿)는 마지막 순번으로 저장한다.
- 카드별로 검증하고(card_validators) 입력의 모든 영역에 통과한 카드가 하나씩 있어야 받아들인다. 아니면 전체를 다시 요청한다(최대 2회).
- 일시 오류(시간 초과, 429, 5xx)는 대기 시간을 늘려 가며 최대 3회 다시 보낸다(1, 2, 4초, 가정).
- 받아들일 응답이 없으면 실행은 failed다. 있으면 report 행 하나와 action_suggestion 행을 저장한다(실행마다 쌓는다, SQ-8).
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
from app.llm.card_validators import CardFilterResult, filter_cards, parse_cards
from app.llm.output_schemas.suggestion import SCHEMA_NAME, SUGGESTION_SCHEMA
from app.llm.prompts.suggestion import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.models import (
    ActionSuggestion, AnalysisSnapshot, LlmCallLog, PipelineRun, ProductFamily, Report, Round, SurveyQuestion,
)
from app.services.action_cards import AREA_QUESTION_CODE, Area, render_area_card, review_card, select_areas

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


def option_labels(session: Session, round_id: int) -> dict[str, str]:
    """q08 보기 코드 -> 라벨. survey_question.options_json에서 읽는다."""
    options = session.scalar(
        select(SurveyQuestion.options_json).where(SurveyQuestion.round_id == round_id, SurveyQuestion.code == AREA_QUESTION_CODE)
    )
    return {option["code"]: option["label"] for option in (options or [])}


def areas_for(session: Session, snapshot: AnalysisSnapshot) -> list[Area]:
    return select_areas(snapshot.table_json, snapshot.allowed_evidence_json, option_labels(session, snapshot.round_id))


def prompts_for_areas(areas: list[Area]) -> tuple[str, str]:
    return SYSTEM_PROMPT, build_user_prompt([{"area_code": a.code, "label": a.label, "rank_label": a.rank_label} for a in areas])


def build_prompts(session: Session, snapshot: AnalysisSnapshot) -> tuple[str, str]:
    return prompts_for_areas(areas_for(session, snapshot))


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
        areas = areas_for(session, snapshot)
        system_prompt, user_prompt = prompts_for_areas(areas)

        counters = {
            "proposed": 0,
            "accepted": 0,
            "dropped_no_evidence": 0,
            "dropped_number_mismatch": 0,
            "dropped_other": 0,
            "dropped_reasons": {},  # dropped_other의 사유 코드별 건수(문장 본문은 저장하지 않는다)
            "areas": len(areas),
            "attempts": 0,
            "llm_calls": 0,
        }
        final: CardFilterResult | None = None
        error_code: str | None = None
        stop = False
        call_no = 0

        if not areas:  # 개선 영역 후보가 없으면 모델을 부르지 않는다
            error_code = ERROR_NO_SUGGESTIONS
            stop = True

        for attempt in range(0 if stop else 1 + MAX_VALIDATION_RETRIES):
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
                        attempt_no=call_no, status="api_error", item_count=len(areas), latency_ms=latency_ms,
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
            parsed = parse_cards(result.text)
            filtered = CardFilterResult()
            if parsed.problem is None:
                filtered = filter_cards(parsed.items, areas)
            session.add(
                LlmCallLog(
                    run_id=run_id, call_type=CALL_TYPE, model_name=model_name, prompt_version=PROMPT_VERSION,
                    attempt_no=call_no, status="ok" if filtered.complete else "invalid_output", item_count=len(areas),
                    latency_ms=latency_ms, error_code=parsed.problem, input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens, created_at=now(),
                )
            )
            final = filtered
            for key in ("proposed", "accepted", "dropped_no_evidence", "dropped_number_mismatch", "dropped_other"):
                counters[key] = filtered.counters[key]  # 마지막으로 검증한 시도의 건수
            counters["dropped_reasons"] = dict(filtered.dropped_reasons)
            if filtered.complete:
                break
            error_code = ERROR_INVALID_OUTPUT if parsed.problem else ERROR_NO_SUGGESTIONS
            if cost_guard is not None and cost_guard.exceeded:
                error_code = ERROR_COST_LIMIT
                break

        accepted = final.accepted if final is not None and final.complete else []
        if accepted:
            report = Report(round_id=round_row.round_id, family_id=family.family_id, run_id=run_id, generated_at=now())
            session.add(report)
            session.flush()
            cards = [
                (
                    render_area_card(card["area"], card["priority_sentence"], card["deliverable_kind"], card["deliverable_text"]),
                    list(card["area"].row_ids),
                )
                for card in accepted
            ]
            review = review_card(rows_by_id)  # 쿠팡 리뷰 카드는 코드 템플릿이다(모델 호출 없음)
            if review is not None:
                cards.append(review)
            for order_no, (sentence, row_ids) in enumerate(cards, start=1):
                session.add(
                    ActionSuggestion(
                        report_id=report.report_id, snapshot_id=snapshot_id, order_no=order_no, sentence=sentence, row_ids=row_ids,
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
