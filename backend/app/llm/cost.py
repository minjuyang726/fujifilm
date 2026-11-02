"""호출 A(광고성 판정)의 비용 가드. 계산만 하고 DB나 OpenAI를 모른다. 리뷰 본문은 글자 수로만 다룬다.

- 호출 전 예상 비용(상한)을 계산해 한도를 넘으면 호출하지 않는다.
- 실행 중에는 호출이 돌려준 실제 토큰 수로 누적 비용을 보고 한도를 넘으면 남은 묶음을 보내지 않는다.
- 보정 값은 CALIBRATION 한 곳에만 둔다. 초기값은 시험 호출 1회(2026-11-02, 영어 가짜 문장 1건)의 실측과 가정이다.
  한국어 입력과 10건 묶음으로 잰 값이 생기면 사용자가 OK 한 뒤에 이 한 곳만 고친다.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Calibration:
    # 호출 한 번의 고정 입력 토큰(시스템 프롬프트, 스키마, 안내문). 실측 326토큰은 항목 1건을 포함한 값이라 상한으로 쓴다.
    fixed_input_tokens: int = 326
    # 항목 하나의 JSON 구조(키, 따옴표, 쉼표) 몫. 가정이며 근거가 없다.
    item_overhead_tokens: int = 30
    # 제목+본문 글자 하나당 토큰 수. 가정이며 한국어로는 측정하지 않았다. 보수적으로 크게 잡았다.
    tokens_per_char: float = 2.0
    # 호출 한 번의 고정 출력 토큰(results 래퍼). 가정. 시험 호출의 출력 26토큰(항목 1건 포함)에서 추정했다.
    output_tokens_per_call: int = 20
    # 항목 하나의 출력 토큰({"review_id":…,"ad_probability":…}). 가정. 같은 실측에서 보수적으로 올렸다.
    output_tokens_per_item: int = 40
    # 같은 항목이 청구될 수 있는 최대 횟수 = 1 + 검증 실패 재시도 2회(services/ad_judgement.py MAX_VALIDATION_RETRIES).
    # 일시 오류(시간 초과, 429, 5xx) 재시도는 청구되지 않는다고 가정한다. 이 가정이 틀려도 실행 중 누적 검사가 막는다.
    retry_multiplier: int = 3


CALIBRATION = Calibration()


@dataclass(frozen=True)
class Prices:
    """100만 토큰당 단가(USD)."""

    input_per_m: float
    output_per_m: float


@dataclass(frozen=True)
class CostEstimate:
    items: int
    calls: int
    input_tokens: int
    output_tokens: int
    one_pass_usd: float  # 재시도 없이 한 번 보낼 때의 상한
    upper_usd: float  # one_pass_usd × 재시도 배수. 한도와 비교하는 값
    sum_based_upper_usd: float  # 참고: 항목별 합계로 계산한 더 낮은 상한(한도 비교에는 쓰지 않는다)


def token_cost_usd(input_tokens: int, output_tokens: int, prices: Prices) -> float:
    return input_tokens / 1_000_000 * prices.input_per_m + output_tokens / 1_000_000 * prices.output_per_m


def estimate_ad_cost(
    char_counts: list[int], batch_size: int, prices: Prices, calibration: Calibration = CALIBRATION
) -> CostEstimate:
    """char_counts는 보낼 항목마다 (제목 글자 수 + 본문 글자 수)다.

    입력 = 호출 수 × 고정 입력 + 항목 수 × (가장 긴 항목의 토큰 상한)
    출력 = 호출 수 × 호출당 출력 + 항목 수 × 항목당 출력
    상한 = (입력 비용 + 출력 비용) × 재시도 배수
    """
    if batch_size < 1:
        raise ValueError("batch_size는 1 이상이어야 합니다.")
    items = len(char_counts)
    if items == 0:
        return CostEstimate(0, 0, 0, 0, 0.0, 0.0, 0.0)
    calls = math.ceil(items / batch_size)
    item_tokens = [math.ceil(calibration.item_overhead_tokens + calibration.tokens_per_char * chars) for chars in char_counts]
    fixed = calls * calibration.fixed_input_tokens
    input_tokens = fixed + items * max(item_tokens)
    input_tokens_by_sum = fixed + sum(item_tokens)
    output_tokens = calls * calibration.output_tokens_per_call + items * calibration.output_tokens_per_item
    one_pass = token_cost_usd(input_tokens, output_tokens, prices)
    by_sum = token_cost_usd(input_tokens_by_sum, output_tokens, prices)
    return CostEstimate(
        items=items,
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        one_pass_usd=one_pass,
        upper_usd=one_pass * calibration.retry_multiplier,
        sum_based_upper_usd=by_sum * calibration.retry_multiplier,
    )


class CostGuard:
    """실행 중 누적 비용. 호출이 끝날 때마다 record()로 실제 토큰 수를 더한다."""

    def __init__(self, limit_usd: float, prices: Prices, fallback_call_usd: float = 0.0):
        self.limit_usd = limit_usd
        self.prices = prices
        # 토큰 수를 돌려받지 못한 호출은 이 값(호출 한 번의 추정 비용)으로 센다.
        self.fallback_call_usd = fallback_call_usd
        self.spent_usd = 0.0

    def record(self, input_tokens: int | None, output_tokens: int | None) -> None:
        if input_tokens is None or output_tokens is None:
            self.spent_usd += self.fallback_call_usd
        else:
            self.spent_usd += token_cost_usd(input_tokens, output_tokens, self.prices)

    @property
    def exceeded(self) -> bool:
        return self.spent_usd > self.limit_usd


@dataclass(frozen=True)
class CallSample:
    """보정용 표본: 호출 한 번의 항목 수, 글자 수 합계, 실제 토큰 수."""

    items: int
    chars: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class CalibrationSuggestion:
    tokens_per_char: float
    output_tokens_per_item: int
    samples_used: int


def suggest_calibration(samples: list[CallSample], current: Calibration = CALIBRATION) -> CalibrationSuggestion:
    """표본에서 보수적인(가장 큰) 값을 제안한다. 자동으로 반영하지 않는다.

    tokens_per_char = max((입력 − 고정 입력 − 항목 수 × 항목 오버헤드) ÷ 글자 수)
    output_tokens_per_item = max(ceil((출력 − 호출당 출력) ÷ 항목 수))
    고정 입력과 항목 오버헤드는 현재 값을 그대로 쓴다(한 표본만으로는 따로 가를 수 없다).
    """
    usable = [sample for sample in samples if sample.items > 0 and sample.chars > 0]
    if not usable:
        raise ValueError("보정에 쓸 표본이 없습니다.")
    per_char = max(
        (sample.input_tokens - current.fixed_input_tokens - sample.items * current.item_overhead_tokens) / sample.chars
        for sample in usable
    )
    per_item_out = max(
        math.ceil((sample.output_tokens - current.output_tokens_per_call) / sample.items) for sample in usable
    )
    return CalibrationSuggestion(
        tokens_per_char=round(max(per_char, 0.0), 3),
        output_tokens_per_item=max(per_item_out, 0),
        samples_used=len(usable),
    )
