"""A-11(포트폴리오 데모 전용, plan.md 부록 A). 읽기 전용이고 집계 숫자만 돌려준다.

오류 응답의 통일 형식(spec.md 7.1)은 Phase 1에서 만든다. 지금은 FastAPI 기본 처리를 따른다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.demo import ReviewStatsResponse
from app.services.review_stats import get_review_stats

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/review-stats", response_model=ReviewStatsResponse)
def review_stats(session: Session = Depends(get_session)) -> dict:
    return get_review_stats(session)
