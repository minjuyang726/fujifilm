"""A-10: 제안 문장의 근거 목록(쪽 나누기). 읽기 전용이다.

page_size 기본 50, 상한 200(가정, SQ-17 기본안). 정렬은 종류(review, survey) 다음 evidence_id 오름차순. 필터는 kind만.
리뷰 항목은 평점과 날짜만, 설문 항목은 "합성" 라벨만 담는다. 작성자·variant·제목·본문은 없다(FR-2.5).
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ActionSuggestion, AnalysisSnapshot
from app.schemas.read import EvidencePage
from app.services.evidence import evidence_page

router = APIRouter(prefix="/api", tags=["evidence"])

PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 200


@router.get("/suggestions/{suggestion_id}/evidence", response_model=EvidencePage)
def get_suggestion_evidence(
    suggestion_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    kind: Literal["review", "survey"] | None = None,
    session: Session = Depends(get_session),
) -> dict:
    suggestion = session.get(ActionSuggestion, suggestion_id)
    if suggestion is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "제안을 찾을 수 없습니다."})
    snapshot = session.get(AnalysisSnapshot, suggestion.snapshot_id)
    return evidence_page(session, snapshot, suggestion.row_ids, page=page, page_size=page_size, kind=kind)
