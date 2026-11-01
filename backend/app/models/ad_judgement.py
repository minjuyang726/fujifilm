from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdJudgement(Base):
    """리뷰 한 건의 광고성 판정. 글은 삭제하지 않고 가중치만 낮춘다(FR-1.6).

    weight_floor_used와 rule_signals(spec.md 3.2절)는 하한(Q-7)과 규칙(SQ-3)이 정해질 때 추가한다.
    """

    __tablename__ = "ad_judgement"

    judgement_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, ForeignKey("review.review_id"), nullable=False)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipeline_run.run_id"), nullable=False)
    ad_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 1 - ad_probability. 가중치 하한이 정해지지 않아 하한은 적용하지 않는다.
    ad_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    judged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'failed', 'skipped')", name="ck_ad_judgement_status"),
        CheckConstraint(
            "ad_probability IS NULL OR (ad_probability >= 0 AND ad_probability <= 1)",
            name="ck_ad_judgement_probability",
        ),
        # 값을 지어내지 않는다: 확률은 status가 ok일 때만 있다.
        CheckConstraint(
            "(status = 'ok' AND ad_probability IS NOT NULL) OR (status <> 'ok' AND ad_probability IS NULL)",
            name="ck_ad_judgement_ok_has_probability",
        ),
        UniqueConstraint("review_id", "run_id", name="uq_ad_judgement_review_run"),
        Index("ix_ad_judgement_run_id", "run_id"),
    )
