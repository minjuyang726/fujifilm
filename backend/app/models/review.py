from datetime import date as date_type

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Review(Base):
    """쿠팡 리뷰. 열은 spec.md 3.1절을 따른다.

    author, seller, source_file, original_no는 적재하지 않는다.
    """

    __tablename__ = "review"

    review_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    product_name: Mapped[str] = mapped_column(Text, ForeignKey("product.product_name"), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    variant: Mapped[str | None] = mapped_column(Text, nullable=True)
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_review_rating"),
        CheckConstraint("helpful_count >= 0", name="ck_review_helpful_count"),
        Index("ix_review_product_name_date", "product_name", "date"),
        Index("ix_review_rating", "rating"),
    )
