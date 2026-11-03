from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NaverSearchCount(Base):
    """네이버 검색 API가 보고한 검색 결과 총 건수(total). 제한 구현(A안, 결정 2026-11-03, 사용자 선택)이라 집계 숫자만 저장한다.

    글의 제목, 요약, 링크, 블로거·카페 이름, 날짜는 저장하지 않고 LLM에도 보내지 않는다. 수치는 실측(네이버가 보고한 값)이고
    수집한 글 건수가 아니라 질의에 대한 검색 결과 수다.
    """

    __tablename__ = "naver_search_count"

    count_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)  # blog 또는 cafearticle
    query: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("source IN ('blog', 'cafearticle')", name="ck_naver_search_count_source"),
        CheckConstraint("total >= 0", name="ck_naver_search_count_total"),
        Index("ix_naver_search_count_query", "source", "query", "collected_at"),
    )
