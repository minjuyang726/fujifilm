"""읽기 API(A-1, A-2, A-4)의 응답 형태. 작성자(author)와 변형(variant)은 필드 자체가 없다(NFR-S2, FR-2.5)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class FamilyOut(BaseModel):
    family_id: int
    name: str


class FamiliesResponse(BaseModel):
    families: list[FamilyOut]


class RoundOut(BaseModel):
    round_id: int
    label: str
    period_start: date | None
    period_end: date | None


class RoundsResponse(BaseModel):
    rounds: list[RoundOut]


class ReviewEvidence(BaseModel):
    kind: Literal["review"]
    review_id: int
    rating: int
    date: date
    review_text: str | None
    text_source: Literal["review_text", "title"] | None


class SurveyAnswerOut(BaseModel):
    question_text: str
    value: str  # 선택지 라벨(코드가 아니다). 다중선택은 선택 하나당 한 항목


class SurveyRoundOut(BaseModel):
    round_id: int
    label: str


class SurveyEvidence(BaseModel):
    kind: Literal["survey"]
    response_id: int
    synthetic_label: Literal["합성"] | None
    round: SurveyRoundOut
    answers: list[SurveyAnswerOut]


class EvidenceReviewItem(BaseModel):
    kind: Literal["review"]
    evidence_id: int
    rating: int
    date: date


class EvidenceSurveyItem(BaseModel):
    kind: Literal["survey"]
    evidence_id: int
    synthetic_label: Literal["합성"] | None


class EvidencePage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[EvidenceReviewItem | EvidenceSurveyItem]
