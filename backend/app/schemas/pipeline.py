from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, PositiveInt


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite는 시간대 없는 값을 돌려주므로 UTC로 본다."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class AdJudgementRequest(BaseModel):
    """POST 본문. 모르는 필드가 오면 422로 거절한다."""

    model_config = ConfigDict(extra="forbid")

    family_id: int | None = None
    # 필수. 이 리뷰만 판정한다. 파일럿에서는 scripts/pilot_sample.py 결과의 review_ids를 그대로 넣는다.
    # 생략하거나 비우면 검토하지 않은 리뷰가 OpenAI로 나갈 수 있어 422로 거절한다.
    review_ids: list[PositiveInt] = Field(min_length=1)


class RunCreated(BaseModel):
    run_id: int
    step: str
    status: str
    started_at: datetime


class RunDetail(BaseModel):
    """GET /api/runs/{run_id}. 리뷰 본문, 작성자, variant는 담지 않는다."""

    run_id: int
    round_id: int
    family_id: int | None
    step: str
    status: str
    counters: dict
    error_code: str | None
    started_at: datetime
    finished_at: datetime | None
