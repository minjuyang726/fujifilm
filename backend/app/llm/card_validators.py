"""호출 B(suggest-v4 액션 카드) 출력 검증. 카드별로 검증하고, 입력의 모든 영역에 통과한 카드가 하나씩 있어야 응답을 받아들인다.

제외 사유는 기존 dropped_* 체계를 따른다(counters 이름):
- dropped_no_evidence: 입력에 없는 area_code(근거 행이 없다, FR-2.4).
- dropped_number_mismatch: 모델이 쓴 텍스트에 숫자(0-9)나 %, 한글 수량 표현이 있거나, {pct}가 정확히 한 번이 아니다(FR-0.3).
- dropped_other: 빈 문장, 길이 초과, 한 문장이 아님, {rank} 자리표시자 오류, "공동" 직접 사용(순위 라벨 불일치),
  변화·인과 표현, 같은 area_code 중복, 영역 누락, 산출물 종류 오류, 산출물 본문의 빈 값·길이 초과·변화·인과 표현.
값을 채운 뒤의 문장(예: "37.0%", "공동 1순위")에 기존 변화·인과 규칙을 그대로 적용한다. 결과에는 사유 코드만 담고 문장 내용은 담지 않는다.
"""

import json
import re
from dataclasses import dataclass, field

from app.llm.prompts.suggestion import (
    DELIVERABLE_KINDS, MAX_DELIVERABLE_CHARS, MAX_SENTENCE_CHARS, PLACEHOLDER_PCT, PLACEHOLDER_RANK,
)
from app.llm.suggestion_validators import (
    BAD_SCHEMA, DROPPED_NO_EVIDENCE, DROPPED_NUMBER_MISMATCH, DROPPED_OTHER, NOT_JSON, _CAUSAL, _CAUSAL_AFTER_NUMBER,
    _CHANGE_AFTER_NUMBER, _SENTENCE_END, has_korean_quantity,
)
from app.services.action_cards import Area, fill_placeholders

REASON_EMPTY = "empty"
REASON_TOO_LONG = "too_long"
REASON_MULTI_SENTENCE = "multi_sentence"
REASON_BAD_PLACEHOLDER = "bad_placeholder"
REASON_RANK_LABEL = "rank_label_mismatch"
REASON_CHANGE_AFTER_NUMBER = "change_after_number"
REASON_CAUSAL_CONNECTOR = "causal_connector"
REASON_CAUSAL_AFTER_NUMBER = "causal_after_number"
REASON_DUPLICATE_AREA = "duplicate_area"
REASON_MISSING_AREA = "missing_area"
REASON_BAD_KIND = "bad_deliverable_kind"
REASON_DELIVERABLE_EMPTY = "deliverable_empty"
REASON_DELIVERABLE_TOO_LONG = "deliverable_too_long"
REASON_DELIVERABLE_CHANGE_OR_CAUSE = "deliverable_change_or_cause"

_DIGIT = re.compile(r"\d")
# 산출물 본문의 변화·효과 표현. 숫자가 없는 글이라 "숫자 바로 뒤" 규칙(_CHANGE_AFTER_NUMBER)은 걸리지 않으므로 단어 자체를 막는다.
# 영역 이름 속 글자(예: 개선)는 막지 않으려고 "개선"은 목록에서 뺀다.
_CHANGE_OR_EFFECT = re.compile(r"증가|감소|확대|축소|향상|상승|하락|인상|인하|효과|해소|줄어|늘어|높아|낮아")
_BRACE = re.compile(r"[{}]")


@dataclass
class ParsedCards:
    items: list[dict] = field(default_factory=list)  # {"area_code", "priority_sentence", "deliverable_kind", "deliverable_text"}
    problem: str | None = None  # NOT_JSON 또는 BAD_SCHEMA (전체를 다시 요청해야 한다)


_CARD_KEYS = {"area_code", "priority_sentence", "deliverable_kind", "deliverable_text"}


def parse_cards(raw_text: str | None) -> ParsedCards:
    """(1) JSON으로 읽힌다 (2) 스키마와 맞다: cards 배열, 항목마다 네 키가 모두 문자열이고 다른 키는 없다."""
    try:
        parsed = json.loads(raw_text) if raw_text else None
    except (TypeError, ValueError):
        return ParsedCards(problem=NOT_JSON)
    if parsed is None:
        return ParsedCards(problem=NOT_JSON)
    if not isinstance(parsed, dict) or set(parsed) != {"cards"} or not isinstance(parsed["cards"], list):
        return ParsedCards(problem=BAD_SCHEMA)
    items = []
    for entry in parsed["cards"]:
        if not isinstance(entry, dict) or set(entry) != _CARD_KEYS or not all(isinstance(entry[key], str) for key in _CARD_KEYS):
            return ParsedCards(problem=BAD_SCHEMA)
        items.append(dict(entry))
    return ParsedCards(items=items)


def _has_number_or_percent(text: str) -> bool:
    return bool(_DIGIT.search(text) or "%" in text or "％" in text)


def check_card(item: dict, areas_by_code: dict[str, Area], accepted_codes: set[str]) -> tuple[str | None, str | None]:
    """(제외 범주, 사유 코드). 통과하면 (None, None). 사유 코드는 dropped_other일 때만 있다."""
    area = areas_by_code.get(item["area_code"])
    if area is None:
        return DROPPED_NO_EVIDENCE, None
    if item["area_code"] in accepted_codes:
        return DROPPED_OTHER, REASON_DUPLICATE_AREA
    raw = item["priority_sentence"].strip()
    deliverable = item["deliverable_text"].strip()
    if not raw:
        return DROPPED_OTHER, REASON_EMPTY
    # 모델이 쓴 모든 텍스트에는 숫자와 %가 없어야 한다. 숫자와 % 는 코드가 자리표시자로 채운다(FR-0.3).
    if _has_number_or_percent(raw) or _has_number_or_percent(deliverable):
        return DROPPED_NUMBER_MISMATCH, None
    if raw.count(PLACEHOLDER_PCT) != 1:
        return DROPPED_NUMBER_MISMATCH, None
    without_placeholders = raw.replace(PLACEHOLDER_PCT, " ").replace(PLACEHOLDER_RANK, " ")
    if raw.count(PLACEHOLDER_RANK) != 1 or _BRACE.search(without_placeholders):
        return DROPPED_OTHER, REASON_BAD_PLACEHOLDER
    # 순위 라벨은 코드가 정한 것과 같아야 한다: {rank}가 라벨을 채우므로 모델이 "공동"을 따로 쓰면 라벨과 어긋난다.
    if "공동" in raw:
        return DROPPED_OTHER, REASON_RANK_LABEL
    if has_korean_quantity(without_placeholders) or has_korean_quantity(deliverable):
        return DROPPED_NUMBER_MISMATCH, None
    filled = fill_placeholders(raw, area)
    if ("공동" in filled) != area.joint:
        return DROPPED_OTHER, REASON_RANK_LABEL
    if len(filled) > MAX_SENTENCE_CHARS:
        return DROPPED_OTHER, REASON_TOO_LONG
    if "\n" in filled or len(_SENTENCE_END.findall(filled)) > 1:
        return DROPPED_OTHER, REASON_MULTI_SENTENCE
    if _CHANGE_AFTER_NUMBER.search(filled):
        return DROPPED_OTHER, REASON_CHANGE_AFTER_NUMBER
    if _CAUSAL.search(filled):
        return DROPPED_OTHER, REASON_CAUSAL_CONNECTOR
    if _CAUSAL_AFTER_NUMBER.search(filled):
        return DROPPED_OTHER, REASON_CAUSAL_AFTER_NUMBER
    if item["deliverable_kind"] not in DELIVERABLE_KINDS:
        return DROPPED_OTHER, REASON_BAD_KIND
    if not deliverable:
        return DROPPED_OTHER, REASON_DELIVERABLE_EMPTY
    if len(deliverable) > MAX_DELIVERABLE_CHARS:
        return DROPPED_OTHER, REASON_DELIVERABLE_TOO_LONG
    if _CHANGE_OR_EFFECT.search(deliverable) or _CAUSAL.search(deliverable):
        return DROPPED_OTHER, REASON_DELIVERABLE_CHANGE_OR_CAUSE
    return None, None


@dataclass
class CardFilterResult:
    accepted: list[dict] = field(default_factory=list)  # 순위 순서의 {"area", "priority_sentence", "deliverable_kind", "deliverable_text"}
    complete: bool = False  # 입력의 모든 영역에 통과한 카드가 하나씩 있으면 참
    counters: dict = field(
        default_factory=lambda: {"proposed": 0, "accepted": 0, "dropped_no_evidence": 0, "dropped_number_mismatch": 0, "dropped_other": 0}
    )
    dropped_reasons: dict = field(default_factory=dict)  # dropped_other의 사유 코드별 건수


def filter_cards(items: list[dict], areas: list[Area]) -> CardFilterResult:
    """카드별로 검증한다. 영역 누락은 dropped_other(missing_area)로 센다. 모든 영역이 채워져야 complete다."""
    result = CardFilterResult()
    areas_by_code = {area.code: area for area in areas}
    accepted: dict[str, dict] = {}
    for item in items:
        result.counters["proposed"] += 1
        category, reason = check_card(item, areas_by_code, set(accepted))
        if category is None:
            accepted[item["area_code"]] = item
            result.counters["accepted"] += 1
            continue
        result.counters[category] += 1
        if category == DROPPED_OTHER and reason:
            result.dropped_reasons[reason] = result.dropped_reasons.get(reason, 0) + 1
    missing = [area for area in areas if area.code not in accepted]
    if missing:
        result.counters[DROPPED_OTHER] += len(missing)
        result.dropped_reasons[REASON_MISSING_AREA] = len(missing)
    result.accepted = [
        {
            "area": area,
            "priority_sentence": accepted[area.code]["priority_sentence"].strip(),
            "deliverable_kind": accepted[area.code]["deliverable_kind"],
            "deliverable_text": accepted[area.code]["deliverable_text"].strip(),
        }
        for area in areas
        if area.code in accepted
    ]
    result.complete = bool(areas) and not missing
    return result
