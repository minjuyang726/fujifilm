"""호출 A(광고성 판정)의 비용 가드. 계산만 하고 DB나 OpenAI를 모른다. 리뷰 본문은 글자 수로만 다룬다.

- 호출 전 예상 비용(상한)을 계산해 한도를 넘으면 호출하지 않는다.
- 실행 중에는 호출이 돌려준 실제 토큰 수로 누적 비용을 보고 한도를 넘으면 남은 묶음을 보내지 않는다.
- 보정 값은 CALIBRATION 한 곳에만 둔다. 2026-11-02 시험 호출 두 번(영어 가짜 문장 1건, 한국어 가짜 문장 10건 묶음)의
  실측으로 보정했다(사용자 승인). 두 측정만으로 낸 값이라 표본이 적고 실제 리뷰(이모지, 숫자, 영문 단어)는 더 높을 수 있다.
  새 측정이 생기면 사용자가 OK 한 뒤에 이 한 곳만 고친다.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Calibration:
    # 호출 한 번의 고정 입력 토큰(시스템 프롬프트, 스키마, 안내문). 470은 ad-v2 파일럿 10개 묶음(각 10건)의 실측 회귀
    # 입력 = 714 + 0.623 × 글자 수(R² 0.9988, 최대 잔차 54토큰)에서 나온 절편 714에서 항목 오버헤드 30 × 10건 = 300을
    # 뺀 값(414)에 여유 56(최대 잔차 54토큰과 비슷한 크기)을 더한 값이다. 한계: 모든 묶음이 10건이라 고정 입력과 항목 오버헤드를 분리하지 못했다
    # (714 = 고정 + 10 × 오버헤드). 오버헤드 30은 가정이고, 이전의 임시 여유 +300은 없앴다.
    fixed_input_tokens: int = 470
    # 항목 하나의 JSON 구조(키, 따옴표, 쉼표) 몫. 한 표본으로 분리할 수 없어(0~30) 가정 30을 유지한다.
    item_overhead_tokens: int = 30
    # 제목+본문 글자 하나당 토큰 수. 한국어 10건 묶음 실측(입력 1,254, 글자 1,400)에서 0.48~0.68(상한 0.677)이고,
    # 실제 리뷰가 더 높을 수 있어 약 18% 여유를 두어 0.80으로 한다.
    tokens_per_char: float = 0.80
    # 호출 한 번의 고정 출력 토큰(results 래퍼). 가정 유지. 실측 기울기의 절편은 약 0이다(출력 26토큰/1건, 316토큰/10건).
    output_tokens_per_call: int = 20
    # 항목 하나의 출력 토큰({"review_id":…,"ad_probability":…}). 시험 호출의 기울기 약 32토큰/항목에서 출발했고,
    # 파일럿 10개 묶음의 실측에 맞춰 40 → 50으로 올렸다.
    output_tokens_per_item: int = 50
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


@dataclass(frozen=True)
class SuggestionCalibration:
    """호출 B(액션 카드 서술, suggest-v4)의 비용 추정 계수. suggest-v4는 아직 실제로 불러 본 적이 없어서 모두 가정이다(실측 아님).

    - 입력: 시스템 프롬프트와 사용자 프롬프트(영역 3개)의 글자 수 × 글자당 토큰. 0.80은 호출 A에서 한국어 리뷰로 잰 값의 상한이다.
    - 출력: 카드 3개 × (우선순위 문장 120자 + 산출물 200자 = 320자 × 글자당 토큰 + 카드당 구조 토큰) + 고정 토큰.
      (suggest-v3의 가정 "문장 5개 × (120자 + 40토큰) + 20 = 820"은 실제 909토큰으로 한 번 부족했다.)
    - 재시도 배수: 같은 요청이 청구될 수 있는 최대 횟수 = 1 + 전체 재요청 2회.
    """

    tokens_per_char: float = 0.80
    output_tokens_per_char: float = 1.0
    output_overhead_per_sentence: int = 60  # 카드당(필드 이름, 산출물 종류 포함) 구조 토큰
    output_fixed_tokens: int = 20
    max_sentences: int = 3  # 카드 수(개선 영역 상위 3개)
    max_sentence_chars: int = 320  # 카드당 글자 수 = 우선순위 문장 120 + 산출물 200
    retry_multiplier: int = 3


SUGGESTION_CALIBRATION = SuggestionCalibration()


def estimate_suggestion_cost(
    system_chars: int, user_chars: int, prices: Prices, calibration: SuggestionCalibration = SUGGESTION_CALIBRATION
) -> CostEstimate:
    """호출 B 한 번(재시도 없음)의 비용과, 재시도 배수를 곱한 상한. 실제 표 크기(user_chars)로 계산한다."""
    input_tokens = math.ceil(calibration.tokens_per_char * (system_chars + user_chars))
    per_sentence = math.ceil(calibration.max_sentence_chars * calibration.output_tokens_per_char) + calibration.output_overhead_per_sentence
    output_tokens = calibration.output_fixed_tokens + calibration.max_sentences * per_sentence
    one_pass = token_cost_usd(input_tokens, output_tokens, prices)
    return CostEstimate(
        items=1,
        calls=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        one_pass_usd=one_pass,
        upper_usd=one_pass * calibration.retry_multiplier,
        sum_based_upper_usd=one_pass * calibration.retry_multiplier,
    )


@dataclass(frozen=True)
class QuestionCalibration:
    """호출 C(다음 회차 문항 초안)의 비용 추정 계수. 호출 C는 아직 실제로 불러 본 적이 없어서 모두 가정이다(실측 아님).

    출력 = 고정 토큰 + 문항 수(가설 수, 최대 5) x (문항 100자 + 선택지 6개 x (30자 + 구조 10토큰) + 문항 구조 40토큰). 글자당 출력 토큰은 1.0이다.
    호출 B에서 출력 토큰 가정(820)이 한 번 부족했던 일이 있어(실제 909) 선택지를 최대 길이로 잡았다.
    """

    tokens_per_char: float = 0.80
    output_tokens_per_char: float = 1.0
    max_questions: int = 5
    max_question_chars: int = 100
    max_options: int = 6
    max_option_chars: int = 30
    option_overhead_tokens: int = 10
    question_overhead_tokens: int = 40
    output_fixed_tokens: int = 20
    retry_multiplier: int = 3


QUESTION_CALIBRATION = QuestionCalibration()


def estimate_question_cost(
    system_chars: int, user_chars: int, prices: Prices, hypothesis_count: int, calibration: QuestionCalibration = QUESTION_CALIBRATION
) -> CostEstimate:
    """호출 C 한 번(재시도 없음)의 비용과, 재시도 배수를 곱한 상한. 실제 프롬프트 글자 수와 가설 수로 계산한다."""
    questions = min(max(hypothesis_count, 0), calibration.max_questions)
    input_tokens = math.ceil(calibration.tokens_per_char * (system_chars + user_chars))
    per_question = (
        math.ceil(calibration.max_question_chars * calibration.output_tokens_per_char)
        + calibration.max_options * (math.ceil(calibration.max_option_chars * calibration.output_tokens_per_char) + calibration.option_overhead_tokens)
        + calibration.question_overhead_tokens
    )
    output_tokens = calibration.output_fixed_tokens + questions * per_question
    one_pass = token_cost_usd(input_tokens, output_tokens, prices)
    return CostEstimate(
        items=questions,
        calls=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        one_pass_usd=one_pass,
        upper_usd=one_pass * calibration.retry_multiplier,
        sum_based_upper_usd=one_pass * calibration.retry_multiplier,
    )
