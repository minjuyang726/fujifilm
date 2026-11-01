"""환경 값 읽기. 값은 backend/.env 또는 환경 변수에서 온다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

# backend/.env가 없어도 오류가 나지 않는다.
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_CORS_ORIGINS = "http://localhost:5173"


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    cors_origins: list[str]


def get_settings() -> Settings:
    raw_origins = os.getenv("CORS_ORIGINS") or DEFAULT_CORS_ORIGINS
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    return Settings(
        database_url=os.getenv("DATABASE_URL") or None,
        cors_origins=origins,
    )
