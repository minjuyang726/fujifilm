"""비용 가드의 계산. 모두 가짜 값이고 네트워크를 쓰지 않는다."""

import pytest

from app.config import get_settings
from app.llm.cost import (
    CALIBRATION,
    CallSample,
    Calibration,
    CostGuard,
    Prices,
    estimate_ad_cost,
    suggest_calibration,
    token_cost_usd,
)
from app.services import ad_judgement as service

PRICES = Prices(input_per_m=0.20, output_per_m=1.20)


def test_calibration_constants_are_the_documented_ones():
    assert CALIBRATION == Calibration(
        fixed_input_tokens=311,
        item_overhead_tokens=30,
        tokens_per_char=0.80,
        output_tokens_per_call=20,
        output_tokens_per_item=40,
        retry_multiplier=3,
    )


def test_retry_multiplier_follows_the_validation_retry_count_in_the_service():
    assert CALIBRATION.retry_multiplier == 1 + service.MAX_VALIDATION_RETRIES


def test_token_cost_matches_the_hand_calculation_of_the_trial_call():
    # 시험 호출(2026-11-02): 입력 326, 출력 26 -> 약 $0.0000964
    assert token_cost_usd(326, 26, PRICES) == pytest.approx(0.0000964, rel=1e-6)


def test_estimate_for_a_pilot_of_100_items_all_at_the_longest_length():
    estimate = estimate_ad_cost([968] * 100, 10, PRICES)
    assert estimate.items == 100 and estimate.calls == 10
    # 입력 = 10 × 311 + 100 × ceil(30 + 0.80 × 968) = 3,110 + 80,500 = 83,610, 출력 = 10 × 20 + 100 × 40 = 4,200
    assert (estimate.input_tokens, estimate.output_tokens) == (83_610, 4_200)
    assert estimate.one_pass_usd == pytest.approx(0.021762, rel=1e-6)
    assert estimate.upper_usd == pytest.approx(0.065286, rel=1e-6)


def test_estimate_uses_the_longest_item_for_every_item_and_the_sum_is_only_a_reference():
    estimate = estimate_ad_cost([10, 10, 1000], 10, PRICES)
    longest = 30 + 0.80 * 1000
    assert estimate.input_tokens == 311 + 3 * longest
    assert estimate.sum_based_upper_usd < estimate.upper_usd


def test_estimate_rounds_the_call_count_up_and_handles_no_items():
    assert estimate_ad_cost([1] * 11, 10, PRICES).calls == 2
    empty = estimate_ad_cost([], 10, PRICES)
    assert (empty.items, empty.calls, empty.upper_usd) == (0, 0, 0.0)


def test_estimate_rejects_a_bad_batch_size():
    with pytest.raises(ValueError):
        estimate_ad_cost([1], 0, PRICES)


def test_guard_adds_real_tokens_and_uses_the_fallback_when_tokens_are_missing():
    guard = CostGuard(limit_usd=0.001, prices=PRICES, fallback_call_usd=0.0004)
    guard.record(1_000_000, 0)  # $0.20
    assert guard.spent_usd == pytest.approx(0.20)
    assert guard.exceeded
    fallback = CostGuard(limit_usd=0.001, prices=PRICES, fallback_call_usd=0.0004)
    fallback.record(None, None)
    fallback.record(100, None)
    assert fallback.spent_usd == pytest.approx(0.0008)
    assert not fallback.exceeded
    fallback.record(None, 5)
    assert fallback.exceeded


def test_estimate_stays_above_the_measured_trial_batch():
    # 2026-11-02 시험 호출 #2: 한국어 가짜 문장 10건(글자 수 아래), 실측 입력 1,254 / 출력 316토큰
    estimate = estimate_ad_cost([50] * 7 + [60, 80, 910], 10, PRICES)
    assert estimate.input_tokens >= 1254
    assert estimate.output_tokens >= 316
    assert estimate.one_pass_usd >= token_cost_usd(1254, 316, PRICES)


OLD_CALIBRATION = Calibration(
    fixed_input_tokens=326, item_overhead_tokens=30, tokens_per_char=2.0,
    output_tokens_per_call=20, output_tokens_per_item=40, retry_multiplier=3,
)


def test_suggestion_takes_the_largest_conservative_values():
    samples = [
        # (3260 - 326 - 10 * 30) / 1300 = 2.0, (180 - 20) / 10 = 16
        CallSample(items=10, chars=1300, input_tokens=3260, output_tokens=180),
        # (700 - 326 - 3 * 30) / 100 = 2.84, (80 - 20) / 3 = 20
        CallSample(items=3, chars=100, input_tokens=700, output_tokens=80),
        CallSample(items=0, chars=0, input_tokens=326, output_tokens=20),  # 쓸 수 없는 표본은 건너뛴다
    ]
    suggestion = suggest_calibration(samples, OLD_CALIBRATION)  # 계산 예시를 고정하려고 이전 계수를 명시한다
    assert suggestion.tokens_per_char == 2.84
    assert suggestion.output_tokens_per_item == 20
    assert suggestion.samples_used == 2
    with pytest.raises(ValueError):
        suggest_calibration([])


def test_settings_read_cost_values_and_never_echo_a_bad_value(monkeypatch):
    monkeypatch.setenv("AD_JUDGEMENT_COST_LIMIT_USD", "0.25")
    settings = get_settings()
    assert settings.ad_judgement_cost_limit_usd == 0.25
    assert (settings.price_input_per_m, settings.price_output_per_m) == (0.20, 1.20)

    monkeypatch.delenv("AD_JUDGEMENT_COST_LIMIT_USD")
    assert get_settings().ad_judgement_cost_limit_usd == 0.5  # 기본 한도

    monkeypatch.delenv("OPENAI_PRICE_INPUT_PER_M")
    assert get_settings().price_input_per_m is None  # 비어 있으면 None

    for bad in ("abc", "-1.5", "0.0", "nan", "inf"):
        monkeypatch.setenv("OPENAI_PRICE_OUTPUT_PER_M", bad)
        with pytest.raises(RuntimeError) as caught:
            get_settings()
        assert "OPENAI_PRICE_OUTPUT_PER_M" in str(caught.value)
        assert bad not in str(caught.value).replace("OPENAI_PRICE_OUTPUT_PER_M", "")
