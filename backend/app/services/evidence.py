"""제안 문장의 근거 계산(SP-3, SQ-17). 근거는 저장하지 않고 스냅샷의 허용 목록에서 계산한다.

문장의 근거 = 문장이 참조한 행(row_ids)의 허용 목록의 합집합. 표에 없는 row_id는 무시한다.
"""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalysisSnapshot, Review, SurveyResponse

Kind = Literal["review", "survey"]
KIND_ORDER = ("review", "survey")  # 정렬은 종류(review, survey) 다음 evidence_id 오름차순이다(구현에서 정함)


def evidence_by_kind(allowed_evidence: dict, row_ids: list[str]) -> dict[str, list[int]]:
    """{"review": [정렬된 review_id], "survey": [정렬된 response_id]}"""
    found: dict[str, set[int]] = {"review": set(), "survey": set()}
    for row_id in row_ids:
        entry = allowed_evidence.get(row_id)
        if entry and entry["kind"] in found:
            found[entry["kind"]].update(entry["ids"])
    return {kind: sorted(found[kind]) for kind in KIND_ORDER}


def evidence_counts(snapshot: AnalysisSnapshot, row_ids: list[str]) -> dict[str, int]:
    grouped = evidence_by_kind(snapshot.allowed_evidence_json, row_ids)
    return {kind: len(grouped[kind]) for kind in KIND_ORDER}


def evidence_page(
    session: Session, snapshot: AnalysisSnapshot, row_ids: list[str], *, page: int, page_size: int, kind: Kind | None
) -> dict:
    grouped = evidence_by_kind(snapshot.allowed_evidence_json, row_ids)
    pairs = [(k, i) for k in KIND_ORDER if kind in (None, k) for i in grouped[k]]
    total = len(pairs)
    window = pairs[(page - 1) * page_size : page * page_size]
    review_ids = [i for k, i in window if k == "review"]
    survey_ids = [i for k, i in window if k == "survey"]
    reviews = {
        r.review_id: r
        for r in session.execute(select(Review.review_id, Review.rating, Review.date).where(Review.review_id.in_(review_ids)))
    } if review_ids else {}
    synthetic = (
        dict(session.execute(select(SurveyResponse.response_id, SurveyResponse.is_synthetic).where(SurveyResponse.response_id.in_(survey_ids))).all())
        if survey_ids
        else {}
    )
    items = []
    for k, i in window:
        if k == "review":
            review = reviews.get(i)
            if review is not None:
                items.append({"kind": "review", "evidence_id": i, "rating": review.rating, "date": review.date})
        else:
            items.append({"kind": "survey", "evidence_id": i, "synthetic_label": "합성" if synthetic.get(i) else None})
    return {"total": total, "page": page, "page_size": page_size, "items": items}
