from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AnalysisSnapshot(Base):
    """분석 스냅샷: 제품군 x 회차마다 코드가 계산한 표 하나. 호출 B의 입력이고 나중에 숫자 일치를 확인하는 근거다(FR-0.2, 0.3)."""

    __tablename__ = "analysis_snapshot"

    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipeline_run.run_id"), nullable=False)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("round.round_id"), nullable=False)
    family_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_family.family_id"), nullable=False)
    # {"family", "round", "rows": [{row_id, group, item, source, metrics, small_sample, ...}]}. 리뷰 본문은 담지 않는다.
    table_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # {row_id: {"kind": "survey" | "review", "ids": [정수, ...]}}. 이 행에 들어간 응답·리뷰의 ID(SP-3). LLM에는 보내지 않는다.
    allowed_evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_analysis_snapshot_round_family", "round_id", "family_id"),)


class Report(Base):
    """회차 리포트. Phase 5는 action-suggestions 실행마다 1행을 만들고(family_id 포함) Phase 6에서 문항 초안과 합친다(SQ-13)."""

    __tablename__ = "report"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(Integer, ForeignKey("round.round_id"), nullable=False)
    family_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("product_family.family_id"), nullable=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipeline_run.run_id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_report_round_family", "round_id", "family_id"),)


class ActionSuggestion(Base):
    """액션 제안 문장 하나. 근거 ID는 저장하지 않고 row_ids로 스냅샷의 허용 목록에서 계산한다(SQ-17)."""

    __tablename__ = "action_suggestion"

    suggestion_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, ForeignKey("report.report_id"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(Integer, ForeignKey("analysis_snapshot.snapshot_id"), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    row_ids: Mapped[list] = mapped_column(JSON, nullable=False)

    __table_args__ = (UniqueConstraint("report_id", "order_no", name="uq_action_suggestion_report_order"),)
