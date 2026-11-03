from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Hypothesis(Base):
    """불확실·불일치 가설(kind 값은 uncertain / contradictory). 코드 규칙(R1~R4)이 스냅샷 표에서 찾고 진술문은 코드가 템플릿으로 만든다(G5, 결정 2026-11-03)."""

    __tablename__ = "hypothesis"

    hypothesis_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("analysis_snapshot.snapshot_id"), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("round.round_id"), nullable=False)
    family_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_family.family_id"), nullable=False)
    # spec.md 3.2의 열 정의에 없던 추가(결정 2026-11-03): 가설을 만든 next-survey-draft 실행
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_run.run_id"), nullable=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    related_row_ids: Mapped[list] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        CheckConstraint("kind IN ('uncertain', 'contradictory')", name="ck_hypothesis_kind"),
        Index("ix_hypothesis_snapshot_id", "snapshot_id"),
    )


class NextSurveyQuestion(Base):
    """다음 회차 설문지의 문항 초안. status는 항상 draft다(FR-3.3). 최신 초안 = 해당 report의 가장 큰 run_id."""

    __tablename__ = "next_survey_question"

    question_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, ForeignKey("report.report_id"), nullable=False)
    # 영역 확인 문항(코드 템플릿)은 가설이 없어 NULL이다(question-v4, 마이그레이션 b3defd1eaa82)
    hypothesis_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("hypothesis.hypothesis_id"), nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("pipeline_run.run_id"), nullable=True)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # scale5/single/multi(question-v3 이전): [{"code": "1", "label": "…"}, …] 순서 유지.
    # scale10/scale10_matrix(question-v4): {"kind", "low_label", "high_label", "items": [{"code", "label"}, …]}. 읽는 쪽은 app/services/question_forms.py의 normalize_question이 두 형식을 같게 다룬다.
    options_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")

    __table_args__ = (
        CheckConstraint("type IN ('scale5', 'single', 'multi', 'scale10', 'scale10_matrix')", name="ck_next_survey_question_type"),
        CheckConstraint("status = 'draft'", name="ck_next_survey_question_status"),
        Index("ix_next_survey_question_report_run", "report_id", "run_id"),
    )
