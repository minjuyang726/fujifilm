"""화면용 읽기 API: A-1(제품군 목록), A-2(회차 목록), A-4(근거: 리뷰와 설문 응답). 모두 읽기 전용이다."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ProductFamily, Review, Round, SurveyAnswer, SurveyQuestion, SurveyResponse
from app.schemas.read import FamiliesResponse, ReviewEvidence, RoundsResponse, SurveyEvidence

router = APIRouter(prefix="/api", tags=["read"])

TEMP_ROUND_PREFIX = "[파일럿-임시]"  # 임시 회차 식별 규칙(plan.md Phase 0c, 결정 2026-11-03)


@router.get("/families", response_model=FamiliesResponse)
def list_families(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(select(ProductFamily).order_by(ProductFamily.family_id)).all()
    return {"families": [{"family_id": row.family_id, "name": row.name} for row in rows]}


@router.get("/rounds", response_model=RoundsResponse)
def list_rounds(session: Session = Depends(get_session)) -> dict:
    rows = session.scalars(
        select(Round).where(~Round.label.startswith(TEMP_ROUND_PREFIX, autoescape=True)).order_by(Round.round_id)
    ).all()
    return {
        "rounds": [
            {"round_id": r.round_id, "label": r.label, "period_start": r.period_start, "period_end": r.period_end}
            for r in rows
        ]
    }


@router.get("/evidence/{kind}/{evidence_id}", response_model=ReviewEvidence | SurveyEvidence)
def get_evidence(kind: Literal["review", "survey"], evidence_id: int, session: Session = Depends(get_session)) -> dict:
    if kind == "survey":
        return _survey_evidence(session, evidence_id)
    # 필요한 열만 읽는다. author는 적재하지 않았고, title은 본문이 없을 때만 본문 자리에 쓴다(SQ-15 기본안).
    row = session.execute(
        select(Review.review_id, Review.rating, Review.date, Review.review_text, Review.title).where(
            Review.review_id == evidence_id
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "근거를 찾을 수 없습니다."})
    if row.review_text:
        text, source = row.review_text, "review_text"
    elif row.title:
        text, source = row.title, "title"
    else:
        text, source = None, None  # 제목·본문이 모두 없는 글(구현에서 정함)
    return {
        "kind": "review",
        "review_id": row.review_id,
        "rating": row.rating,
        "date": row.date,
        "review_text": text,
        "text_source": source,
    }


def _survey_evidence(session: Session, response_id: int) -> dict:
    """설문 응답 한 건. 답은 문항 순서대로, 값은 선택지 라벨이다. 합성 응답이면 "합성" 라벨이 붙는다(FR-1.10)."""
    response = session.get(SurveyResponse, response_id)
    if response is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "근거를 찾을 수 없습니다."})
    round_row = session.get(Round, response.round_id)
    rows = session.execute(
        select(SurveyQuestion.text, SurveyQuestion.options_json, SurveyAnswer.value)
        .join(SurveyAnswer, SurveyAnswer.question_id == SurveyQuestion.question_id)
        .where(SurveyAnswer.response_id == response_id)
        .order_by(SurveyQuestion.question_id, SurveyAnswer.answer_id)
    ).all()
    answers = []
    for text, options, value in rows:
        labels = {option["code"]: option["label"] for option in options}
        answers.append({"question_text": text, "value": labels.get(value, value)})
    return {
        "kind": "survey",
        "response_id": response.response_id,
        "synthetic_label": "합성" if response.is_synthetic else None,
        "round": {"round_id": round_row.round_id, "label": round_row.label},
        "answers": answers,
    }
