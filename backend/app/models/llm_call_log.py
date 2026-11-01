from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LlmCallLog(Base):
    """LLM 호출 한 번의 기록. 요청·응답 원문은 저장하지 않는다(spec.md 6.1절)."""

    __tablename__ = "llm_call_log"

    call_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("pipeline_run.run_id"), nullable=False)
    call_type: Mapped[str] = mapped_column(Text, nullable=False)  # 호출 A는 "A"
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    # 아래 다섯 열은 spec.md 6.1절(시도 횟수, 상태, 지연 시간)에 맞춰 추가했다.
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)  # ok, invalid_output, api_error
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_llm_call_log_run_id", "run_id"),)
