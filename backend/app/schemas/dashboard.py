"""A-3(대시보드 API)의 응답 형태: family, round, survey(Phase 2), voc(Phase 4)."""

from typing import Literal

from pydantic import BaseModel


class DashboardFamily(BaseModel):
    family_id: int
    name: str


class DashboardRound(BaseModel):
    round_id: int
    label: str


class OptionResult(BaseModel):
    # 선택지 코드(문자열)와 라벨. 코드는 Table Editor의 survey_answer.value와 맞춰 볼 때 쓴다.
    code: str
    option: str
    count: int
    ratio: float


class QuestionResult(BaseModel):
    question_id: int
    text: str
    type: Literal["scale5", "single", "multi"]
    results: list[OptionResult]


class SurveySection(BaseModel):
    respondent_count: int
    synthetic_label: Literal["합성"] | None
    scope: Literal["common"]
    questions: list[QuestionResult]


class RatingCell(BaseModel):
    rating: int
    count: float  # 비가중과 미판정·제목·본문 없음은 정수, 가중은 가중치의 합


class AggregateOut(BaseModel):
    """판정 묶음의 집계. 비가중이면 count가 글 수, 가중이면 가중치의 합이다."""

    count: float
    mean_rating: float | None
    rating_distribution: list[RatingCell]


class VocCounts(BaseModel):
    total: int
    judged: int
    unjudged: int
    no_text: int


class UnjudgedOut(BaseModel):
    count: int
    failed_count: int
    rating_distribution: list[RatingCell]


class NoTextOut(BaseModel):
    count: int
    rating_distribution: list[RatingCell]


class ExcludedOut(BaseModel):
    count: int
    other_round_count: int
    outside_rounds_count: int


class VocSection(BaseModel):
    weight_floor: float
    small_sample_threshold: int
    small_sample: bool
    counts: VocCounts
    unweighted: AggregateOut
    weighted: AggregateOut
    unjudged: UnjudgedOut
    no_text: NoTextOut
    excluded: ExcludedOut


class DashboardResponse(BaseModel):
    family: DashboardFamily
    round: DashboardRound
    survey: SurveySection
    voc: VocSection
