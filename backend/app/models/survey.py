from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProductFamily(Base):
    """제품군. 열은 spec.md 3.2절의 product_family와 같다. 시드(행)는 Phase 1에서 넣는다."""

    __tablename__ = "product_family"

    family_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class SurveyQuestion(Base):
    """회차별 설문 문항. type은 scale5 / single / multi, options_json은 [{"code": "1", "label": "…"}, …] (순서 유지)."""

    __tablename__ = "survey_question"

    question_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("round.round_id"), nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    options_json: Mapped[list] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        CheckConstraint("type IN ('scale5', 'single', 'multi')", name="ck_survey_question_type"),
        UniqueConstraint("round_id", "code", name="uq_survey_question_round_code"),
    )


class SurveyResponse(Base):
    """응답 한 건. 합성 응답은 is_synthetic이 항상 참이다(DR-2). 공통 설문이라 family_id는 NULL(SQ-5 결정)."""

    __tablename__ = "survey_response"

    response_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("round.round_id"), nullable=False)
    family_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("product_family.family_id"), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (Index("ix_survey_response_round_id", "round_id"),)


class SurveyAnswer(Base):
    """응답의 답 한 칸. value는 선택지 코드(문자열)이고, 다중선택은 선택 하나당 한 행이다."""

    __tablename__ = "survey_answer"

    answer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    response_id: Mapped[int] = mapped_column(Integer, ForeignKey("survey_response.response_id"), nullable=False)
    question_id: Mapped[int] = mapped_column(Integer, ForeignKey("survey_question.question_id"), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_survey_answer_response_id", "response_id"),
        Index("ix_survey_answer_question_id", "question_id"),
    )
