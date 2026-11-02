"""환경 값 읽기. 값은 backend/.env 또는 환경 변수에서 온다."""

import math
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

# 한 번의 광고성 판정 실행에서 예상되는 비용 상한(USD). 넘으면 호출 전에 중단한다(사용자 결정 2026-11-02, 설계 제안 비용 가드).
DEFAULT_AD_JUDGEMENT_COST_LIMIT_USD = 0.5

# 가중치 하한(prd.md Q-7). 임시 값이고 근거가 약하다. 집계 시점에 max(하한, ad_weight)로 적용하고 저장된 값은 바꾸지 않는다.
DEFAULT_AD_WEIGHT_FLOOR = 0.1

# 판정 묶음의 글 수가 이 값보다 작으면 화면에 "표본 적음"을 붙인다(plan.md G4, 결정 2026-11-03).
# 임시 가정이다. 이 데이터로 검증한 값이 아니고 Q-7처럼 근거가 약하다. 환경 값이 아니라 코드 상수다.
VOC_SMALL_SAMPLE_THRESHOLD = 30


@dataclass(frozen=True)
class Settings:
    # repr에서 뺀다. 설정 객체를 로그나 오류 출력에 그대로 찍어도 접속 문자열과 키가 나오지 않게 한다.
    database_url: str | None = field(repr=False)
    cors_origins: list[str]
    openai_api_key: str | None = field(repr=False)
    openai_model_ad: str | None
    ad_judgement_max_items: int
    ad_judgement_cost_limit_usd: float
    # 가중치 하한. 0 이상 1 미만
    ad_weight_floor: float
    # 100만 토큰당 단가(USD). 비어 있으면 None이고, 이때 실제 호출은 하지 않는다(비용 가드).
    price_input_per_m: float | None
    price_output_per_m: float | None


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


def _float_from_env(name: str, default: float | None) -> float | None:
    """비어 있으면 default. 값이 있으면 0보다 큰 유한한 수여야 한다. 잘못된 값은 값을 출력하지 않고 이름만 알린다."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(f"{name}는 숫자여야 합니다.") from None
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name}는 0보다 큰 수여야 합니다.")
    return value


def _weight_floor_from_env() -> float:
    """AD_WEIGHT_FLOOR: 비어 있으면 0.1. 값이 있으면 0 이상 1 미만의 유한한 수여야 한다. 잘못된 값은 이름만 알린다."""
    raw = os.getenv("AD_WEIGHT_FLOOR")
    if raw is None or raw.strip() == "":
        return DEFAULT_AD_WEIGHT_FLOOR
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError("AD_WEIGHT_FLOOR는 숫자여야 합니다.") from None
    if not math.isfinite(value) or value < 0 or value >= 1:
        raise RuntimeError("AD_WEIGHT_FLOOR는 0 이상 1 미만이어야 합니다.")
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
        ad_judgement_cost_limit_usd=_float_from_env(
            "AD_JUDGEMENT_COST_LIMIT_USD", DEFAULT_AD_JUDGEMENT_COST_LIMIT_USD
        ),
        ad_weight_floor=_weight_floor_from_env(),
        price_input_per_m=_float_from_env("OPENAI_PRICE_INPUT_PER_M", None),
        price_output_per_m=_float_from_env("OPENAI_PRICE_OUTPUT_PER_M", None),
    )
