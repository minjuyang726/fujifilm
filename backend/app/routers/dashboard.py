"""A-3(대시보드 API): 설문(Phase 2)과 외부 VOC(Phase 4). 읽기 전용이다."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import VOC_SMALL_SAMPLE_THRESHOLD, get_settings
from app.db import get_session
from app.models import ProductFamily, Round
from app.routers.read import TEMP_ROUND_PREFIX
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import survey_section
from app.services.voc import voc_section

router = APIRouter(prefix="/api", tags=["dashboard"])


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": message})


@router.get("/families/{family_id}/dashboard", response_model=DashboardResponse)
def get_dashboard(family_id: int, round_id: int, session: Session = Depends(get_session)) -> dict:
    family = session.get(ProductFamily, family_id)
    if family is None:
        raise _not_found("제품군을 찾을 수 없습니다.")
    round_row = session.get(Round, round_id)
    # 임시 회차는 A-2 목록에서 뺀 것과 같은 규칙으로 없는 것처럼 다룬다(결정 2026-11-03)
    if round_row is None or round_row.label.startswith(TEMP_ROUND_PREFIX):
        raise _not_found("회차를 찾을 수 없습니다.")
    # 설문은 제품군과 무관한 공통 설문이라(SQ-5) 제품군은 존재 확인에만 쓴다. 이 응답에서 400은 내지 않는다.
    return {
        "family": {"family_id": family.family_id, "name": family.name},
        "round": {"round_id": round_row.round_id, "label": round_row.label},
        "survey": survey_section(session, round_row.round_id),
        "voc": voc_section(
            session,
            family.family_id,
            round_row,
            weight_floor=get_settings().ad_weight_floor,
            small_sample_threshold=VOC_SMALL_SAMPLE_THRESHOLD,
        ),
    }
