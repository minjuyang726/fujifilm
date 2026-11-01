from datetime import date as date_type

from sqlalchemy import Date, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Round(Base):
    """회차. 열은 spec.md 3.2절의 round와 같다. 설문 관련 테이블은 Phase 0c에서 추가한다."""

    __tablename__ = "round"

    round_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date_type | None] = mapped_column(Date, nullable=True)
