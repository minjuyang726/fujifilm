"""step next-survey-draft: 스냅샷에서 코드 규칙으로 가설을 찾고(R1~R4, LLM 미관여), 가설마다 다음 회차 문항 초안을 호출 C로 쓴다.

- 가설이 0개면 LLM을 부르지 않고 failed(NO_HYPOTHESES)로 끝낸다. 가설은 실행 기록(run_id)과 함께 저장하고 쌓는다(SQ-8).
- 문항은 통과한 것만 해당 report에 붙이고(run_id 포함) status는 항상 draft다(FR-3.3). 최신 초안 = 가장 큰 run_id.
- 재시도 정책은 호출 B와 같다: 일시 오류 대기 1·2·4초 최대 3회, 통과 문항 0개이거나 스키마 오류면 전체를 최대 2회 다시 요청한다.
- 리뷰 본문, 키, LLM 요청·응답 원문은 로그, 실행 기록, llm_call_log 어디에도 남기지 않는다. LLM 입력은 가설의 id, 종류, 진술문뿐이다.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import log_event
from app.llm.client import LLMClient, PermanentLLMError, TransientLLMError
from app.llm.cost import CostGuard
from app.llm.output_schemas.question import QUESTION_SCHEMA, SCHEMA_NAME
from app.llm.prompts.question import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.llm.question_validators import QuestionFilterResult, filter_questions, options_json, parse_questions
from app.models import (
    AnalysisSnapshot, Hypothesis, LlmCallLog, NextSurveyQuestion, PipelineRun, ProductFamily, Report, Round, SurveyQuestion,
)
from app.services.hypotheses import find_hypotheses
from app.services.report_data import report_snapshot_id

logger = logging.getLogger(__name__)

STEP_NAME = "next-survey-draft"
CALL_TYPE = "C"
MAX_VALIDATION_RETRIES = 2
MAX_TRANSIENT_RETRIES = 3
BACKOFF_SECONDS = (1, 2, 4)

ERROR_INTERNAL = "INTERNAL_ERROR"
ERROR_COST_LIMIT = "COST_LIMIT"
ERROR_NO_HYPOTHESES = "NO_HYPOTHESES"
ERROR_NO_QUESTIONS = "NO_QUESTIONS"
ERROR_INVALID_OUTPUT = "INVALID_OUTPUT"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def snapshot_for_report(session: Session, report: Report) -> AnalysisSnapshot | None:
    """리포트의 제안이 쓴 스냅샷(같은 표로 가설을 만든다)."""
    snapshot_id = report_snapshot_id(session, report.report_id)
    return session.get(AnalysisSnapshot, snapshot_id) if snapshot_id is not None else None


def question_types(session: Session, round_id: int) -> dict[str, str]:
    return dict(session.execute(select(SurveyQuestion.code, SurveyQuestion.type).where(SurveyQuestion.round_id == round_id)).all())


def hypotheses_for(session: Session, snapshot: AnalysisSnapshot) -> list[dict]:
    return find_hypotheses(snapshot.table_json, question_types(session, snapshot.round_id))


def prompts_for(hypotheses: list[dict]) -> tuple[str, str]:
    """비용 추정과 실행이 같은 프롬프트를 쓰도록 한 곳에서 만든다. hypotheses에는 hypothesis_id가 있어야 한다."""
    return SYSTEM_PROMPT, build_user_prompt(hypotheses)


def run_next_survey_draft(
    session: Session,
    *,
    round_row: Round,
    family: ProductFamily,
    report: Report,
    snapshot: AnalysisSnapshot,
    client: LLMClient,
    model_name: str,
    cost_guard: CostGuard | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _utc_now,
) -> PipelineRun:
    run = PipelineRun(
        round_id=round_row.round_id, family_id=family.family_id, step=STEP_NAME, status="running", counters={}, started_at=now()
    )
    session.add(run)
    session.commit()
    run_id = run.run_id
    report_id, snapshot_id = report.report_id, snapshot.snapshot_id
    log_event(logger, logging.INFO, "next_survey_draft_start", run_id=run_id, step=STEP_NAME, report_id=report_id)

    try:
        found = hypotheses_for(session, snapshot)
        counters: dict = {
            "hypotheses": len(found),
            "rules": dict(Counter(item["rule"] for item in found)),
            "proposed": 0,
            "accepted": 0,
            "dropped_hypothesis": 0,
            "dropped_format": 0,
            "dropped_number": 0,
            "dropped_reasons": {},
            "attempts": 0,
            "llm_calls": 0,
        }
        if not found:
            run = session.get(PipelineRun, run_id)
            run.status, run.error_code, run.counters, run.finished_at = "failed", ERROR_NO_HYPOTHESES, counters, now()
            session.commit()
            log_event(logger, logging.INFO, "next_survey_draft_end", run_id=run_id, status="failed", error_code=ERROR_NO_HYPOTHESES)
            return run

        stored: list[Hypothesis] = []
        for item in found:
            row = Hypothesis(
                snapshot_id=snapshot_id, round_id=round_row.round_id, family_id=family.family_id, run_id=run_id,
                kind=item["kind"], statement=item["statement"], related_row_ids=item["related_row_ids"],
            )
            session.add(row)
            stored.append(row)
        session.flush()
        for row, item in zip(stored, found):
            item["hypothesis_id"] = row.hypothesis_id
        order_of = {row.hypothesis_id: index for index, row in enumerate(stored)}  # 가설 우선순위 순서로 문항 번호를 매긴다
        system_prompt, user_prompt = prompts_for(found)
        ids = set(order_of)

        final: QuestionFilterResult | None = None
        error_code: str | None = None
        stop = False
        call_no = 0
        for attempt in range(1 + MAX_VALIDATION_RETRIES):
            counters["attempts"] = attempt + 1
            result = None
            transient_retries = 0
            while True:
                call_no += 1
                started = time.perf_counter()
                try:
                    result = client.complete_json(
                        model=model_name, system_prompt=system_prompt, user_prompt=user_prompt,
                        schema_name=SCHEMA_NAME, json_schema=QUESTION_SCHEMA,
                    )
                    problem = None
                except TransientLLMError as error:
                    problem, transient = error.code, True
                except PermanentLLMError as error:
                    problem, transient = error.code, False
                latency_ms = int((time.perf_counter() - started) * 1000)
                counters["llm_calls"] = call_no
                if problem is None:
                    break
                session.add(
                    LlmCallLog(
                        run_id=run_id, call_type=CALL_TYPE, model_name=model_name, prompt_version=PROMPT_VERSION, attempt_no=call_no,
                        status="api_error", item_count=len(found), latency_ms=latency_ms, error_code=problem,
                        input_tokens=None, output_tokens=None, created_at=now(),
                    )
                )
                if not transient or transient_retries >= MAX_TRANSIENT_RETRIES:
                    error_code, stop = problem, True
                    break
                log_event(logger, logging.WARNING, "next_survey_draft_retry", run_id=run_id, error_code=problem, retry=transient_retries + 1)
                sleep(BACKOFF_SECONDS[min(transient_retries, len(BACKOFF_SECONDS) - 1)])
                transient_retries += 1
            if stop:
                break

            if cost_guard is not None:
                cost_guard.record(result.input_tokens, result.output_tokens)
            parsed = parse_questions(result.text)
            filtered = QuestionFilterResult()
            if parsed.problem is None:
                filtered = filter_questions(parsed.items, ids)
            session.add(
                LlmCallLog(
                    run_id=run_id, call_type=CALL_TYPE, model_name=model_name, prompt_version=PROMPT_VERSION, attempt_no=call_no,
                    status="ok" if filtered.accepted else "invalid_output", item_count=len(found), latency_ms=latency_ms,
                    error_code=parsed.problem, input_tokens=result.input_tokens, output_tokens=result.output_tokens, created_at=now(),
                )
            )
            final = filtered
            for key in ("proposed", "accepted", "dropped_hypothesis", "dropped_format", "dropped_number"):
                counters[key] = filtered.counters[key]  # 마지막으로 검증한 시도의 건수
            counters["dropped_reasons"] = dict(filtered.dropped_reasons)
            if filtered.accepted:
                break
            error_code = ERROR_INVALID_OUTPUT if parsed.problem else ERROR_NO_QUESTIONS
            if cost_guard is not None and cost_guard.exceeded:
                error_code = ERROR_COST_LIMIT
                break

        accepted = sorted(final.accepted, key=lambda item: order_of[item["hypothesis_id"]]) if final is not None else []
        if accepted:
            for order_no, item in enumerate(accepted, start=1):
                session.add(
                    NextSurveyQuestion(
                        report_id=report_id, hypothesis_id=item["hypothesis_id"], run_id=run_id, order_no=order_no,
                        text=item["text"], type=item["type"], options_json=options_json(item["type"], item["options"]), status="draft",
                    )
                )
            status, error_code = "succeeded", None
        else:
            status, error_code = "failed", error_code or ERROR_NO_QUESTIONS
        run = session.get(PipelineRun, run_id)
        run.status, run.counters, run.error_code, run.finished_at = status, counters, error_code, now()
        session.commit()
        log_event(logger, logging.INFO, "next_survey_draft_end", run_id=run_id, step=STEP_NAME, status=status, error_code=error_code,
                  hypotheses=counters["hypotheses"], accepted=counters["accepted"], attempts=counters["attempts"])
        return run
    except Exception as error:  # 오류 메시지에 요청 내용이 들어갈 수 있어 종류만 기록한다.
        session.rollback()
        failed_run = session.get(PipelineRun, run_id)
        failed_run.status, failed_run.error_code, failed_run.finished_at = "failed", ERROR_INTERNAL, now()
        session.commit()
        log_event(logger, logging.ERROR, "next_survey_draft_failed", run_id=run_id, step=STEP_NAME, error_type=type(error).__name__)
        return failed_run
