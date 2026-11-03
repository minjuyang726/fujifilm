"""호출 C 출력 검증(question-v4). 문항별로 검증하고 통과하지 못한 문항은 쓰지 않는다.

모델은 문구(text, low_label, high_label)만 쓴다. 형식·선택지·항목이 출력에 오면 스키마(parse_questions)가 막는다: 정해진 네 키 외의 키가 있으면
BAD_SCHEMA로 응답 전체를 다시 요청한다.
제외 범주(counters): dropped_hypothesis(입력에 없는 hypothesis_id, 같은 가설에 둘째 문항),
dropped_format(빈 문항, 길이 초과, 양끝 라벨의 빈 값·길이 초과·같은 라벨, 문항이 항목 이름을 나열함),
dropped_number(문항이나 양끝 라벨에 아라비아 숫자 또는 한글 수량 표현이 있음 - 새 수치 없음, FR-0.3),
dropped_meta(문항이나 양끝 라벨에 표본|VOC|수집된|판정|합성|가설이 있음 - 응답자에게 데이터·분석을 언급하지 않음). 세부 사유 코드는 dropped_reasons에 센다.
결과에는 사유 코드만 담고 문항 내용은 담지 않는다. 양끝 라벨의 "의미가 반대"인지는 코드가 가릴 수 없어서 프롬프트로만 지시한다(같은 라벨만 막는다).
"""

import json
import re
from dataclasses import dataclass, field

from app.llm.prompts.question import MAX_LABEL_CHARS, MAX_QUESTION_CHARS
from app.llm.card_validators import BAD_SCHEMA, NOT_JSON, has_korean_quantity

DROPPED_HYPOTHESIS = "dropped_hypothesis"
DROPPED_FORMAT = "dropped_format"
DROPPED_NUMBER = "dropped_number"
DROPPED_META = "dropped_meta"

REASON_UNKNOWN_HYPOTHESIS = "unknown_hypothesis"
REASON_DUPLICATE_HYPOTHESIS = "duplicate_hypothesis"
REASON_EMPTY_TEXT = "empty_text"
REASON_TEXT_TOO_LONG = "text_too_long"
REASON_BAD_LABEL = "bad_scale_label"  # 양끝 라벨이 비었거나 14자를 넘음
REASON_SAME_LABELS = "same_scale_labels"
REASON_LISTS_OPTIONS = "lists_options"
REASON_HAS_NUMBER = "has_number"
REASON_META_WORD = "meta_word"

LIST_OPTIONS_MIN = 2  # 문항이 같은 가설의 항목 이름을 이만큼 이상 쓰면 나열로 본다

_DIGIT = re.compile(r"\d")
# VOC는 영문자 사이에 낀 경우(예: vocal)는 단어가 아니므로 뺀다. 나머지는 한글 단어 일부로 걸린다("가설치"처럼 정상 단어에 들어 있어도 걸리는 한계가 있다).
_META_WORDS = re.compile(r"표본|수집된|판정|합성|가설|(?<![A-Za-z])VOC(?![A-Za-z])", re.IGNORECASE)
_QUESTION_KEYS = {"hypothesis_id", "text", "low_label", "high_label"}


@dataclass
class ParsedQuestions:
    items: list[dict] = field(default_factory=list)  # {"hypothesis_id", "text", "low_label", "high_label"}
    problem: str | None = None  # NOT_JSON 또는 BAD_SCHEMA (전체를 다시 요청해야 한다)


def parse_questions(raw_text: str | None) -> ParsedQuestions:
    """(1) JSON으로 읽힌다 (2) 스키마와 맞다: questions 배열, 항목마다 hypothesis_id(정수), text·low_label·high_label(문자열)만. 다른 키(type, options, items)는 막는다."""
    try:
        parsed = json.loads(raw_text) if raw_text else None
    except (TypeError, ValueError):
        return ParsedQuestions(problem=NOT_JSON)
    if parsed is None:
        return ParsedQuestions(problem=NOT_JSON)
    if not isinstance(parsed, dict) or set(parsed) != {"questions"} or not isinstance(parsed["questions"], list):
        return ParsedQuestions(problem=BAD_SCHEMA)
    items = []
    for entry in parsed["questions"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != _QUESTION_KEYS
            or not isinstance(entry["hypothesis_id"], int)
            or isinstance(entry["hypothesis_id"], bool)
            or not all(isinstance(entry[key], str) for key in ("text", "low_label", "high_label"))
        ):
            return ParsedQuestions(problem=BAD_SCHEMA)
        items.append(dict(entry))
    return ParsedQuestions(items=items)


def contains_number(text: str) -> bool:
    return bool(_DIGIT.search(text) or has_korean_quantity(text))


def contains_meta_word(text: str) -> bool:
    return bool(_META_WORDS.search(text))


def check_question(
    item: dict, hypothesis_ids: set[int], accepted_ids: set[int], item_labels: dict[int, list[str]] | None = None
) -> tuple[str | None, str | None]:
    """(범주, 사유 코드). 통과하면 (None, None). item_labels: {hypothesis_id: 코드가 공급하는 항목 이름들}."""
    if item["hypothesis_id"] not in hypothesis_ids:
        return DROPPED_HYPOTHESIS, REASON_UNKNOWN_HYPOTHESIS
    if item["hypothesis_id"] in accepted_ids:
        return DROPPED_HYPOTHESIS, REASON_DUPLICATE_HYPOTHESIS
    text = item["text"].strip()
    low, high = item["low_label"].strip(), item["high_label"].strip()
    if not text:
        return DROPPED_FORMAT, REASON_EMPTY_TEXT
    if len(text) > MAX_QUESTION_CHARS:
        return DROPPED_FORMAT, REASON_TEXT_TOO_LONG
    if not low or not high or len(low) > MAX_LABEL_CHARS or len(high) > MAX_LABEL_CHARS:
        return DROPPED_FORMAT, REASON_BAD_LABEL
    if low.replace(" ", "") == high.replace(" ", ""):
        return DROPPED_FORMAT, REASON_SAME_LABELS
    labels = (item_labels or {}).get(item["hypothesis_id"], [])
    if sum(1 for label in labels if label and label in text) >= LIST_OPTIONS_MIN:
        return DROPPED_FORMAT, REASON_LISTS_OPTIONS
    if any(contains_meta_word(part) for part in (text, low, high)):
        return DROPPED_META, REASON_META_WORD
    if any(contains_number(part) for part in (text, low, high)):
        return DROPPED_NUMBER, REASON_HAS_NUMBER
    return None, None


@dataclass
class QuestionFilterResult:
    accepted: list[dict] = field(default_factory=list)  # {"hypothesis_id", "text", "low_label", "high_label"}(공백 정리됨)
    counters: dict = field(
        default_factory=lambda: {"proposed": 0, "accepted": 0, "dropped_hypothesis": 0, "dropped_format": 0, "dropped_number": 0, "dropped_meta": 0}
    )
    dropped_reasons: dict = field(default_factory=dict)


def filter_questions(items: list[dict], hypothesis_ids: set[int], item_labels: dict[int, list[str]] | None = None) -> QuestionFilterResult:
    result = QuestionFilterResult()
    accepted_ids: set[int] = set()
    for item in items:
        result.counters["proposed"] += 1
        category, reason = check_question(item, hypothesis_ids, accepted_ids, item_labels)
        if category is None:
            accepted_ids.add(item["hypothesis_id"])
            result.accepted.append(
                {
                    "hypothesis_id": item["hypothesis_id"],
                    "text": item["text"].strip(),
                    "low_label": item["low_label"].strip(),
                    "high_label": item["high_label"].strip(),
                }
            )
            result.counters["accepted"] += 1
            continue
        result.counters[category] += 1
        result.dropped_reasons[reason] = result.dropped_reasons.get(reason, 0) + 1
    return result
