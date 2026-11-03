"""A-8 일반화: POST /api/rounds/{round_id}/pipeline/{step} (analysis-snapshot, action-suggestions).

기존 ad-judgement 경로(app/routers/pipeline.py)는 그대로 두고, 이 라우터는 그 뒤에 등록되어 나머지 단계를 받는다.
본문은 {"family_id": 정수}이고 두 단계 모두 필수다(스냅샷이 제품군 x 회차 단위라서, 구현에서 정함).
서버가 요청 안에서 끝까지 실행한 뒤 201을 돌려준다(백그라운드 실행 아님).
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import VOC_SMALL_SAMPLE_THRESHOLD, get_settings
from app.db import get_session
from app.models import ProductFamily, Round
from app.routers.read import TEMP_ROUND_PREFIX
from app.schemas.pipeline import RunCreated, as_utc
from app.services.snapshot_step import STEP_NAME as SNAPSHOT_STEP
from app.services.snapshot_step import run_analysis_snapshot

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


@router.post("/rounds/{round_id}/pipeline/{step}", status_code=201, response_model=RunCreated)
def run_step(round_id: int, step: str, body: StepRequest, session: Session = Depends(get_session)) -> RunCreated:
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
    raise _error(400, "BAD_REQUEST", "이 단계는 아직 지원하지 않습니다.")
