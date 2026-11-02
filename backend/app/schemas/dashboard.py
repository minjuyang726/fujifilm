"""A-3(대시보드 API)의 응답 형태. Phase 2는 설문 부분만 돌려준다. voc 필드는 Phase 4에서 채운다(결정 2026-11-03)."""

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


class DashboardResponse(BaseModel):
    family: DashboardFamily
    round: DashboardRound
    survey: SurveySection
