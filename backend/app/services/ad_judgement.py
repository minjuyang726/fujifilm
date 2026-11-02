"""호출 A(광고성 판정)의 묶음 요청·검증·재시도 로직. DB를 모르고 리뷰 본문을 기록하지 않는다.

spec.md 6.3절: 네트워크·시간 초과·429·5xx는 같은 요청을 대기 후 다시 보내고, 출력 검증에 실패한 항목은
그 항목만 다시 요청한다. 끝내 실패한 항목은 failed로 두고 값을 지어내지 않는다.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.llm.client import LLMClient, PermanentLLMError, TransientLLMError
from app.llm.output_schemas.ad_judgement import AD_JUDGEMENT_SCHEMA, SCHEMA_NAME
from app.llm.prompts.ad_judgement import SYSTEM_PROMPT, build_user_prompt
from app.llm.validators import validate_ad_judgement

logger = logging.getLogger(__name__)

# 아래 네 값은 가정이다. spec.md SQ-9(배치 크기, 재시도 횟수·대기 시간)가 정해지지 않았다.
BATCH_SIZE = 10
MAX_TRANSIENT_RETRIES = 3
MAX_VALIDATION_RETRIES = 2
BACKOFF_SECONDS = (1.0, 2.0, 4.0)

ERROR_INVALID_OUTPUT = "INVALID_OUTPUT"
ERROR_COST_LIMIT = "COST_LIMIT"


@dataclass(frozen=True)
class ReviewInput:
    review_id: int
    title: str | None
    review_text: str | None


@dataclass
class Outcome:
    review_id: int
    status: str  # "ok" 또는 "failed"
    ad_probability: float | None = None
    error_code: str | None = None


@dataclass
class CallRecord:
    attempt_no: int
    status: str  # ok, invalid_output, api_error
    item_count: int
    latency_ms: int
    error_code: str | None
    input_tokens: int | None
    output_tokens: int | None


@dataclass
class JudgeReport:
    outcomes: list[Outcome] = field(default_factory=list)
    not_run: list[int] = field(default_factory=list)  # 영구 오류나 비용 한도로 중단되어 보내지 못한 항목
    aborted: bool = False
    cost_stopped: bool = False  # 실행 중 누적 비용이 한도를 넘어 중단했다


def _noop(_record: CallRecord) -> None:
    return None


def _never() -> bool:
    return False


def _judge_batch(
    client: LLMClient,
    model: str,
    batch: list[ReviewInput],
    *,
    sleep: Callable[[float], None],
    clock: Callable[[], float],
    on_call: Callable[[CallRecord], None],
    should_stop: Callable[[], bool] = _never,
) -> tuple[list[Outcome], bool]:
    """한 묶음을 판정한다. (결과, 영구 오류로 중단했는지)를 돌려준다.

    should_stop이 참이면(비용 한도 초과) 다시 요청하지 않고 남은 항목을 failed(COST_LIMIT)로 둔다.
    """
    by_id = {review.review_id: review for review in batch}
    pending = [review.review_id for review in batch]
    outcomes: dict[int, Outcome] = {}
    validation_retries = 0
    attempt_no = 0

    def fail_pending(code: str) -> None:
        for review_id in pending:
            outcomes[review_id] = Outcome(review_id, "failed", error_code=code)

    while pending:
        if should_stop():
            fail_pending(ERROR_COST_LIMIT)
            break
        items = [
            {"review_id": review_id, "title": by_id[review_id].title, "review_text": by_id[review_id].review_text}
            for review_id in pending
        ]
        user_prompt = build_user_prompt(items)

        transient_retries = 0
        while True:
            attempt_no += 1
            started = clock()
            try:
                result = client.complete_json(
                    model=model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    schema_name=SCHEMA_NAME,
                    json_schema=AD_JUDGEMENT_SCHEMA,
                )
            except TransientLLMError as error:
                on_call(CallRecord(attempt_no, "api_error", len(items), int((clock() - started) * 1000), error.code, None, None))
                if transient_retries < MAX_TRANSIENT_RETRIES:
                    delay = BACKOFF_SECONDS[min(transient_retries, len(BACKOFF_SECONDS) - 1)]
                    transient_retries += 1
                    logger.warning("광고성 판정 재시도 code=%s retry=%d", error.code, transient_retries)
                    sleep(delay)
                    continue
                fail_pending(error.code)
                return [outcomes[review.review_id] for review in batch], False
            except PermanentLLMError as error:
                on_call(CallRecord(attempt_no, "api_error", len(items), int((clock() - started) * 1000), error.code, None, None))
                fail_pending(error.code)
                return [outcomes[review.review_id] for review in batch if review.review_id in outcomes], True
            break

        validation = validate_ad_judgement(result.text, pending)
        problem_code = None if validation.fully_valid else ",".join(sorted(validation.problems)) or ERROR_INVALID_OUTPUT
        on_call(
            CallRecord(
                attempt_no,
                "ok" if validation.fully_valid else "invalid_output",
                len(items),
                int((clock() - started) * 1000),
                problem_code,
                result.input_tokens,
                result.output_tokens,
            )
        )
        for review_id, probability in validation.accepted.items():
            outcomes[review_id] = Outcome(review_id, "ok", ad_probability=probability)
        pending = list(validation.rejected)
        if pending:
            if validation_retries < MAX_VALIDATION_RETRIES:
                validation_retries += 1
                logger.warning("광고성 판정 출력 검증 실패, 실패 항목만 다시 요청 retry=%d items=%d", validation_retries, len(pending))
                continue
            fail_pending(ERROR_INVALID_OUTPUT)
            break

    return [outcomes[review.review_id] for review in batch], False


def judge_reviews(
    client: LLMClient,
    model: str,
    reviews: list[ReviewInput],
    *,
    batch_size: int = BATCH_SIZE,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    on_call: Callable[[CallRecord], None] = _noop,
    should_stop: Callable[[], bool] = _never,
) -> JudgeReport:
    """reviews를 batch_size건씩 묶어 판정한다. 영구 오류(인증 등)가 나면 남은 묶음은 보내지 않는다.

    should_stop은 묶음을 보내기 전에 확인한다(비용 한도). 참이면 남은 묶음은 보내지 않고 not_run으로 둔다.
    """
    if batch_size < 1:
        raise ValueError("batch_size는 1 이상이어야 합니다.")
    report = JudgeReport()
    for start in range(0, len(reviews), batch_size):
        if should_stop():
            report.cost_stopped = True
            report.not_run = [review.review_id for review in reviews[start:]]
            break
        batch = reviews[start : start + batch_size]
        outcomes, aborted = _judge_batch(
            client, model, batch, sleep=sleep, clock=clock, on_call=on_call, should_stop=should_stop
        )
        if any(outcome.error_code == ERROR_COST_LIMIT for outcome in outcomes):
            report.cost_stopped = True
        report.outcomes.extend(outcomes)
        if aborted:
            report.aborted = True
            report.not_run = [review.review_id for review in reviews[start + len(batch) :]]
            break
    return report
