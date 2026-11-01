"""LLM 출력 검증(spec.md 6.3절 호출 A).

통과하지 못한 항목은 판정으로 쓰지 않는다. 결과에는 문제 종류(코드)만 담고 값은 담지 않는다.
"""

import json
import math
from collections import Counter
from dataclasses import dataclass, field

# 검증 문제 종류
NOT_JSON = "not_json"
BAD_SCHEMA = "bad_schema"
LENGTH_MISMATCH = "length_mismatch"
UNKNOWN_ID = "unknown_id"
DUPLICATE_ID = "duplicate_id"
BAD_PROBABILITY = "bad_probability"
BAD_ITEM = "bad_item"


@dataclass
class ValidationResult:
    accepted: dict[int, float] = field(default_factory=dict)  # review_id -> ad_probability
    rejected: list[int] = field(default_factory=list)  # 입력 순서대로. 다시 요청할 항목
    problems: set[str] = field(default_factory=set)

    @property
    def fully_valid(self) -> bool:
        return not self.rejected and not self.problems


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_ad_judgement(raw_text: str | None, input_ids: list[int]) -> ValidationResult:
    """raw_text(JSON 문자열)를 입력 review_id 목록에 맞춰 검증한다."""
    result = ValidationResult()

    def reject_all(problem: str) -> ValidationResult:
        result.problems.add(problem)
        result.rejected = list(input_ids)
        return result

    # (1) JSON으로 읽힌다
    try:
        parsed = json.loads(raw_text) if raw_text else None
    except (TypeError, ValueError):
        return reject_all(NOT_JSON)
    if parsed is None:
        return reject_all(NOT_JSON)

    # (2) 스키마와 맞다: results 배열, 항목마다 review_id(정수)와 ad_probability(숫자)만
    if not isinstance(parsed, dict) or set(parsed) != {"results"} or not isinstance(parsed["results"], list):
        return reject_all(BAD_SCHEMA)

    entries = parsed["results"]
    valid_entries: list[tuple[int, float]] = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"review_id", "ad_probability"}
            or isinstance(entry["review_id"], bool)
            or not isinstance(entry["review_id"], int)
            or not _is_number(entry["ad_probability"])
        ):
            result.problems.add(BAD_ITEM)
            continue
        valid_entries.append((entry["review_id"], float(entry["ad_probability"])))

    # (3) results 길이가 입력과 같다
    if len(entries) != len(input_ids):
        result.problems.add(LENGTH_MISMATCH)

    # (4) review_id가 입력에 있고 중복이 없다
    allowed = set(input_ids)
    counts = Counter(review_id for review_id, _ in valid_entries)
    if any(review_id not in allowed for review_id in counts):
        result.problems.add(UNKNOWN_ID)
    duplicated = {review_id for review_id, count in counts.items() if count > 1}
    if duplicated:
        result.problems.add(DUPLICATE_ID)

    # (5) ad_probability가 0 이상 1 이하의 유한한 수다
    for review_id, probability in valid_entries:
        if review_id not in allowed or review_id in duplicated:
            continue
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            result.problems.add(BAD_PROBABILITY)
            continue
        result.accepted[review_id] = probability

    result.rejected = [review_id for review_id in input_ids if review_id not in result.accepted]
    return result
