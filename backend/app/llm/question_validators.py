"""호출 C 출력 검증(spec.md 6.3절 호출 C). 문항별로 검증하고 통과하지 못한 문항은 쓰지 않는다.

제외 범주(counters): dropped_hypothesis(입력에 없는 hypothesis_id, 같은 가설에 둘째 문항), dropped_format(빈 문항, 길이 초과, type·options 형식 오류),
dropped_number(문항이나 선택지에 아라비아 숫자 또는 한글 수량 표현이 있음 - 새 수치 없음, FR-0.3),
dropped_meta(문항이나 선택지에 표본|VOC|수집된|판정|합성|가설이 있음 - 응답자에게 데이터·분석을 언급하지 않음, question-v2). 세부 사유 코드는 dropped_reasons에 센다.
결과에는 사유 코드만 담고 문항 내용은 담지 않는다. scale5의 1~5는 코드가 채우므로 숫자 검사 대상이 아니다.
"""

import json
import re
from dataclasses import dataclass, field

from app.llm.prompts.question import MAX_OPTION_CHARS, MAX_OPTIONS, MAX_QUESTION_CHARS, MIN_OPTIONS
from app.llm.suggestion_validators import BAD_SCHEMA, NOT_JSON, has_korean_quantity

TYPES = ("scale5", "single", "multi")

DROPPED_HYPOTHESIS = "dropped_hypothesis"
DROPPED_FORMAT = "dropped_format"
DROPPED_NUMBER = "dropped_number"
DROPPED_META = "dropped_meta"

REASON_UNKNOWN_HYPOTHESIS = "unknown_hypothesis"
REASON_DUPLICATE_HYPOTHESIS = "duplicate_hypothesis"
REASON_EMPTY_TEXT = "empty_text"
REASON_TEXT_TOO_LONG = "text_too_long"
REASON_BAD_TYPE = "bad_type"
REASON_BAD_OPTIONS = "bad_options"
REASON_HAS_NUMBER = "has_number"
REASON_META_WORD = "meta_word"

_DIGIT = re.compile(r"\d")
# VOC는 영문자 사이에 낀 경우(예: vocal)는 단어가 아니므로 뺀다. 나머지는 한글 단어 일부로 걸린다("가설치"처럼 정상 단어에 들어 있어도 제외되는 것이 알려진 한계).
_META_WORDS = re.compile(r"표본|수집된|판정|합성|가설|(?<![A-Za-z])VOC(?![A-Za-z])", re.IGNORECASE)


@dataclass
class ParsedQuestions:
    items: list[dict] = field(default_factory=list)  # {"hypothesis_id", "text", "type", "options"}
    problem: str | None = None  # NOT_JSON 또는 BAD_SCHEMA (전체를 다시 요청해야 한다)


def parse_questions(raw_text: str | None) -> ParsedQuestions:
    """(1) JSON으로 읽힌다 (2) 스키마와 맞다: questions 배열, 항목마다 hypothesis_id(정수), text(문자열), type(문자열), options(문자열 배열 또는 null)만."""
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
            or set(entry) != {"hypothesis_id", "text", "type", "options"}
            or not isinstance(entry["hypothesis_id"], int)
            or isinstance(entry["hypothesis_id"], bool)
            or not isinstance(entry["text"], str)
            or not isinstance(entry["type"], str)
            or not (entry["options"] is None or (isinstance(entry["options"], list) and all(isinstance(o, str) for o in entry["options"])))
        ):
            return ParsedQuestions(problem=BAD_SCHEMA)
        items.append(dict(entry))
    return ParsedQuestions(items=items)


def contains_number(text: str) -> bool:
    return bool(_DIGIT.search(text) or has_korean_quantity(text))


def contains_meta_word(text: str) -> bool:
    return bool(_META_WORDS.search(text))


def check_question(item: dict, hypothesis_ids: set[int], accepted_ids: set[int]) -> tuple[str | None, str | None]:
    """(범주, 사유 코드). 통과하면 (None, None)."""
    if item["hypothesis_id"] not in hypothesis_ids:
        return DROPPED_HYPOTHESIS, REASON_UNKNOWN_HYPOTHESIS
    if item["hypothesis_id"] in accepted_ids:
        return DROPPED_HYPOTHESIS, REASON_DUPLICATE_HYPOTHESIS
    text = item["text"].strip()
    if not text:
        return DROPPED_FORMAT, REASON_EMPTY_TEXT
    if len(text) > MAX_QUESTION_CHARS:
        return DROPPED_FORMAT, REASON_TEXT_TOO_LONG
    kind, options = item["type"], item["options"]
    if kind not in TYPES:
        return DROPPED_FORMAT, REASON_BAD_TYPE
    if kind == "scale5":
        if options is not None:
            return DROPPED_FORMAT, REASON_BAD_OPTIONS
    else:
        cleaned = [o.strip() for o in (options or [])]
        if (
            options is None
            or not (MIN_OPTIONS <= len(cleaned) <= MAX_OPTIONS)
            or any(not o or len(o) > MAX_OPTION_CHARS for o in cleaned)
            or len(set(cleaned)) != len(cleaned)
        ):
            return DROPPED_FORMAT, REASON_BAD_OPTIONS
    if contains_meta_word(text) or any(contains_meta_word(o) for o in (options or [])):
        return DROPPED_META, REASON_META_WORD
    if contains_number(text) or any(contains_number(o) for o in (options or [])):
        return DROPPED_NUMBER, REASON_HAS_NUMBER
    return None, None


@dataclass
class QuestionFilterResult:
    accepted: list[dict] = field(default_factory=list)  # {"hypothesis_id", "text", "type", "options"(정리됨)}
    counters: dict = field(
        default_factory=lambda: {"proposed": 0, "accepted": 0, "dropped_hypothesis": 0, "dropped_format": 0, "dropped_number": 0, "dropped_meta": 0}
    )
    dropped_reasons: dict = field(default_factory=dict)


def filter_questions(items: list[dict], hypothesis_ids: set[int]) -> QuestionFilterResult:
    result = QuestionFilterResult()
    accepted_ids: set[int] = set()
    for item in items:
        result.counters["proposed"] += 1
        category, reason = check_question(item, hypothesis_ids, accepted_ids)
        if category is None:
            accepted_ids.add(item["hypothesis_id"])
            result.accepted.append(
                {
                    "hypothesis_id": item["hypothesis_id"],
                    "text": item["text"].strip(),
                    "type": item["type"],
                    "options": None if item["options"] is None else [o.strip() for o in item["options"]],
                }
            )
            result.counters["accepted"] += 1
            continue
        result.counters[category] += 1
        result.dropped_reasons[reason] = result.dropped_reasons.get(reason, 0) + 1
    return result


def options_json(kind: str, options: list[str] | None) -> list[dict]:
    """저장할 options_json. scale5는 LLM이 아니라 코드가 1~5를 채운다. 순서를 유지한다."""
    if kind == "scale5":
        return [{"code": str(i), "label": f"{i}점"} for i in range(1, 6)]
    return [{"code": str(i), "label": label} for i, label in enumerate(options or [], start=1)]
