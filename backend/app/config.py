"""환경 값 읽기. 값은 backend/.env 또는 환경 변수에서 온다."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent

# backend/.env가 없어도 오류가 나지 않는다.
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_CORS_ORIGINS = "http://localhost:5173"

# 한 번의 광고성 판정 실행에서 LLM에 보내는 글 수의 상한. 310건 전체 실행은 prd.md Q-17-3이 해결된 뒤에
# 이 값을 일부러 올려야만 가능하다(설계 제안, spec.md 6.2절). 파일럿 규모 100건은 가정이다.
DEFAULT_AD_JUDGEMENT_MAX_ITEMS = 100


@dataclass(frozen=True)
class Settings:
    # repr에서 뺀다. 설정 객체를 로그나 오류 출력에 그대로 찍어도 접속 문자열과 키가 나오지 않게 한다.
    database_url: str | None = field(repr=False)
    cors_origins: list[str]
    openai_api_key: str | None = field(repr=False)
    openai_model_ad: str | None
    ad_judgement_max_items: int


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise RuntimeError(f"{name}는 정수여야 합니다.") from None
    if value < 0:
        raise RuntimeError(f"{name}는 0 이상이어야 합니다.")
    return value


def get_settings() -> Settings:
    raw_origins = os.getenv("CORS_ORIGINS") or DEFAULT_CORS_ORIGINS
    origins = [item.strip() for item in raw_origins.split(",") if item.strip()]
    return Settings(
        database_url=os.getenv("DATABASE_URL") or None,
        cors_origins=origins,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model_ad=os.getenv("OPENAI_MODEL_AD") or None,
        ad_judgement_max_items=_int_from_env("AD_JUDGEMENT_MAX_ITEMS", DEFAULT_AD_JUDGEMENT_MAX_ITEMS),
    )
