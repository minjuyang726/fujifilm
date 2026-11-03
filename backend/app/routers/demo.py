"""A-11(집계 검증용 API, plan.md 부록 A). 읽기 전용이고 집계 숫자만 돌려준다.

오류 응답은 app/core/errors.py의 통일 형식(spec.md 7.1)을 따른다.
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
