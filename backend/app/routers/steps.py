"""A-8 일반화: POST /api/rounds/{round_id}/pipeline/{step} (analysis-snapshot, action-suggestions).

기존 ad-judgement 경로(app/routers/pipeline.py)는 그대로 두고, 이 라우터는 그 뒤에 등록되어 나머지 단계를 받는다.
본문은 {"family_id": 정수}이고 두 단계 모두 필수다(스냅샷이 제품군 x 회차 단위라서, 구현에서 정함).
서버가 요청 안에서 끝까지 실행한 뒤 201을 돌려준다(백그라운드 실행 아님).
"""

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import VOC_SMALL_SAMPLE_THRESHOLD, get_settings
from app.db import get_session
from app.llm.client import (
    LLMClient, LLMConfigError, QuestionModelNotConfigured, SuggestModelNotConfigured, get_question_model_name, get_suggest_model_name,
)
from app.llm.cost import CostGuard, Prices, estimate_question_cost, estimate_suggestion_cost
from app.models import PipelineRun, ProductFamily, Round
from app.routers.pipeline import get_llm_client_factory
from app.routers.read import TEMP_ROUND_PREFIX
from app.schemas.pipeline import RunCreated, as_utc
from app.services.hypotheses import question_targets
from app.services.question_step import STEP_NAME as QUESTION_STEP
from app.services.question_step import hypotheses_for, prompts_for, run_next_survey_draft, snapshot_for_report
from app.services.report_data import counts_for_list, latest_report
from app.services.snapshot_step import STEP_NAME as SNAPSHOT_STEP
from app.services.snapshot_step import run_analysis_snapshot
from app.services.suggestion_step import STEP_NAME as SUGGESTION_STEP
from app.services.suggestion_step import build_prompts, latest_snapshot, run_action_suggestions

router = APIRouter(prefix="/api", tags=["pipeline"])

KNOWN_STEPS = ("ad-judgement", "analysis-snapshot", "action-suggestions", "next-survey-draft", "report-assembly")


class StepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: int


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def load_family_and_round(session: Session, family_id: int, round_id: int) -> tuple[ProductFamily, Round]:
    round_row = session.get(Round, round_id)
    if round_row is None or round_row.label.startswith(TEMP_ROUND_PREFIX):
        raise _error(404, "NOT_FOUND", "회차를 찾을 수 없습니다.")
    family = session.get(ProductFamily, family_id)
    if family is None:
        raise _error(404, "NOT_FOUND", "제품군을 찾을 수 없습니다.")
    return family, round_row


def created(run) -> RunCreated:
    return RunCreated(run_id=run.run_id, step=run.step, status=run.status, started_at=as_utc(run.started_at))


def get_suggest_model_provider() -> Callable[[], str]:
    return get_suggest_model_name


def get_question_model_provider() -> Callable[[], str]:
    return get_question_model_name


ASSEMBLY_STEP = "report-assembly"


@router.post("/rounds/{round_id}/pipeline/{step}", status_code=201, response_model=RunCreated)
def run_step(
    round_id: int,
    step: str,
    body: StepRequest,
    session: Session = Depends(get_session),
    client_factory: Callable[[], LLMClient] = Depends(get_llm_client_factory),
    model_provider: Callable[[], str] = Depends(get_suggest_model_provider),
    question_model_provider: Callable[[], str] = Depends(get_question_model_provider),
) -> RunCreated:
    if step not in KNOWN_STEPS:
        raise _error(400, "BAD_REQUEST", "지원하지 않는 단계입니다.")
    if step == SNAPSHOT_STEP:
        family, round_row = load_family_and_round(session, body.family_id, round_id)
        run = run_analysis_snapshot(
            session,
            family=family,
            round_row=round_row,
            weight_floor=get_settings().ad_weight_floor,
            small_sample_threshold=VOC_SMALL_SAMPLE_THRESHOLD,
        )
        return created(run)
    if step == SUGGESTION_STEP:
        family, round_row = load_family_and_round(session, body.family_id, round_id)
        snapshot = latest_snapshot(session, family.family_id, round_row.round_id)
        if snapshot is None:
            raise _error(400, "STEP_NOT_READY", "분석 스냅샷이 없습니다. analysis-snapshot 단계를 먼저 실행해 주세요.")
        try:
            model_name = model_provider()
            client = client_factory()
        except SuggestModelNotConfigured:
            raise _error(500, "MODEL_NOT_CONFIGURED", "액션 제안 모델이 설정되지 않았습니다.") from None
        except LLMConfigError:
            raise _error(500, "LLM_NOT_CONFIGURED", "OpenAI 키가 설정되지 않았습니다.") from None
        # 비용 가드: 호출 전에 실제 표 크기로 예상 비용 상한을 계산한다(호출 A와 같은 단가 설정, 한도는 호출 B용)
        settings = get_settings()
        if settings.price_input_per_m is None or settings.price_output_per_m is None:
            raise _error(500, "PRICE_NOT_CONFIGURED", "비용 가드에 필요한 단가가 설정되지 않아 호출하지 않았습니다.")
        prices = Prices(settings.price_input_per_m, settings.price_output_per_m)
        system_prompt, user_prompt = build_prompts(snapshot)
        estimate = estimate_suggestion_cost(len(system_prompt), len(user_prompt), prices)
        limit = settings.suggestion_cost_limit_usd
        if estimate.upper_usd > limit:
            raise _error(
                422,
                "COST_LIMIT_EXCEEDED",
                f"예상 비용 상한 ${estimate.upper_usd:.4f}가 한도 ${limit:.2f}를 넘어 호출하지 않았습니다.",
            )
        run = run_action_suggestions(
            session,
            round_row=round_row,
            family=family,
            snapshot=snapshot,
            client=client,
            model_name=model_name,
            cost_guard=CostGuard(limit, prices, estimate.one_pass_usd),
        )
        return created(run)
    if step == QUESTION_STEP:
        family, round_row = load_family_and_round(session, body.family_id, round_id)
        report = latest_report(session, family.family_id, round_row.round_id)
        snapshot = snapshot_for_report(session, report) if report is not None else None
        if report is None or snapshot is None:
            raise _error(400, "STEP_NOT_READY", "성공한 액션 제안 리포트가 없습니다. action-suggestions 단계를 먼저 실행해 주세요.")
        try:
            model_name = question_model_provider()
            client = client_factory()
        except QuestionModelNotConfigured:
            raise _error(500, "MODEL_NOT_CONFIGURED", "문항 초안 모델이 설정되지 않았습니다.") from None
        except LLMConfigError:
            raise _error(500, "LLM_NOT_CONFIGURED", "OpenAI 키가 설정되지 않았습니다.") from None
        settings = get_settings()
        if settings.price_input_per_m is None or settings.price_output_per_m is None:
            raise _error(500, "PRICE_NOT_CONFIGURED", "비용 가드에 필요한 단가가 설정되지 않아 호출하지 않았습니다.")
        prices = Prices(settings.price_input_per_m, settings.price_output_per_m)
        found = question_targets(hypotheses_for(session, snapshot))
        system_prompt, user_prompt = prompts_for([{**item, "hypothesis_id": index} for index, item in enumerate(found, start=1)])
        estimate = estimate_question_cost(len(system_prompt), len(user_prompt), prices, len(found))
        limit = settings.question_cost_limit_usd
        if found and estimate.upper_usd > limit:
            raise _error(
                422,
                "COST_LIMIT_EXCEEDED",
                f"예상 비용 상한 ${estimate.upper_usd:.4f}가 한도 ${limit:.2f}를 넘어 호출하지 않았습니다.",
            )
        run = run_next_survey_draft(
            session,
            round_row=round_row,
            family=family,
            report=report,
            snapshot=snapshot,
            client=client,
            model_name=model_name,
            cost_guard=CostGuard(limit, prices, estimate.one_pass_usd),
        )
        return created(run)
    if step == ASSEMBLY_STEP:
        # 얇은 확인 단계: 가장 최근 리포트에 제안과 최신 초안 문항이 모두 1개 이상인지 검사하고 실행 기록만 남긴다(새 데이터 없음).
        family, round_row = load_family_and_round(session, body.family_id, round_id)
        report = latest_report(session, family.family_id, round_row.round_id)
        suggestions, questions = counts_for_list(session, [report.report_id])[report.report_id] if report is not None else (0, 0)
        if report is None or suggestions < 1 or questions < 1:
            raise _error(400, "STEP_NOT_READY", "액션 제안과 문항 초안이 모두 있는 리포트가 없습니다. 선행 단계를 먼저 실행해 주세요.")
        now = datetime.now(timezone.utc)
        run = PipelineRun(
            round_id=round_row.round_id, family_id=family.family_id, step=ASSEMBLY_STEP, status="succeeded",
            counters={"report_id": report.report_id, "suggestions": suggestions, "questions": questions},
            started_at=now, finished_at=now,
        )
        session.add(run)
        session.commit()
        return created(run)
    raise _error(400, "BAD_REQUEST", "이 단계는 아직 지원하지 않습니다.")
