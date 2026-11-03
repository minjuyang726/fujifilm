"""[이전 형식] suggest-v3 호출 B 출력 검증(spec.md 6.3절 호출 B). suggest-v4부터는 단계가 쓰지 않는다(카드 검증은 card_validators.py).
이 모듈의 이전 단위 테스트(tests/test_suggestion_module.py)가 아직 가져다 쓴다. 한글 수량·변화·인과 정규식과 상수는 card_validators.py로 옮겼다.

문장별로 검증하고, 통과하지 못한 문장은 쓰지 않는다.

제외 사유는 세 가지다(plan.md Phase 5, counters 이름):
- dropped_no_evidence: row_ids가 비었거나 표에 없는 row_id가 있거나, 행들의 근거 합집합이 비어 있다(FR-2.4).
- dropped_number_mismatch: 문장 속 숫자가 참조한 행의 값과 일치하지 않거나, 한글 수량 표현(절반, 두 배, 세 건 등)이 있다(FR-0.3).
- dropped_other: 길이 초과, 한 문장이 아님, 합성 표기 누락, 표본 표기 누락, 숫자 뒤의 변화 표현(33% 개선 등), 인과 연결(이므로, 때문에 등), 중복, 문장 개수 초과.
숫자 비교 규칙(결정 2026-11-03): 문장의 아라비아 숫자를 모두 뽑아 참조한 행의 지표 값과 비교한다. 쓴 소수 자리(0~2)로
반올림한 값이 일치하면 통과한다(예: 비율 48.96은 49, 49.0, 48.96 모두 통과). 문항·선택지 라벨, 회차 이름, 제품군 이름, 문항 코드 속 숫자는
비교에서 뺀다. 결과에는 사유 코드만 담고 문장 내용은 담지 않는다.
"""

import json
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.llm.card_validators import (  # noqa: F401  (재사용 정의는 card_validators.py로 옮겼다. 이 모듈의 이전 테스트가 이 이름으로 가져온다)
    _CAUSAL, _CAUSAL_AFTER_NUMBER, _CHANGE_AFTER_NUMBER, _SENTENCE_END, BAD_SCHEMA, DROPPED_NO_EVIDENCE, DROPPED_NUMBER_MISMATCH, DROPPED_OTHER,
    NOT_JSON, has_korean_quantity,
)
from app.llm.prompts.suggestion import MAX_SENTENCE_CHARS, MAX_SENTENCES


# dropped_other의 사유 코드(counters.dropped_reasons에 센다. 문장 본문은 저장하지 않는다)
REASON_EMPTY = "empty"
REASON_TOO_LONG = "too_long"
REASON_MULTI_SENTENCE = "multi_sentence"
REASON_CHANGE_AFTER_NUMBER = "change_after_number"
REASON_CAUSAL_CONNECTOR = "causal_connector"
REASON_CAUSAL_AFTER_NUMBER = "causal_after_number"
REASON_MISSING_SYNTHETIC = "missing_synthetic_word"
REASON_MISSING_SAMPLE = "missing_sample_word"
REASON_DUPLICATE = "duplicate"
REASON_OVER_LIMIT = "over_sentence_limit"

SYNTHETIC_WORD = "합성"
SMALL_SAMPLE_WORD = "표본"



_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")
_CODE = re.compile(r"[qQ]\d+")


@dataclass
class ParsedOutput:
    items: list[dict] = field(default_factory=list)  # {"sentence": str, "row_ids": list[str]}
    problem: str | None = None  # NOT_JSON 또는 BAD_SCHEMA (전체를 다시 요청해야 한다)


def parse_suggestions(raw_text: str | None) -> ParsedOutput:
    """(1) JSON으로 읽힌다 (2) 스키마와 맞다: suggestions 배열, 항목마다 sentence(문자열)와 row_ids(문자열 배열)만."""
    try:
        parsed = json.loads(raw_text) if raw_text else None
    except (TypeError, ValueError):
        return ParsedOutput(problem=NOT_JSON)
    if parsed is None:
        return ParsedOutput(problem=NOT_JSON)
    if not isinstance(parsed, dict) or set(parsed) != {"suggestions"} or not isinstance(parsed["suggestions"], list):
        return ParsedOutput(problem=BAD_SCHEMA)
    items = []
    for entry in parsed["suggestions"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"sentence", "row_ids"}
            or not isinstance(entry["sentence"], str)
            or not isinstance(entry["row_ids"], list)
            or not all(isinstance(x, str) for x in entry["row_ids"])
        ):
            return ParsedOutput(problem=BAD_SCHEMA)
        items.append({"sentence": entry["sentence"], "row_ids": list(entry["row_ids"])})
    return ParsedOutput(items=items)


def _numbers_in(text: str) -> list[str]:
    return _NUMBER.findall(_THOUSANDS.sub("", text))


def _strip_labels(sentence: str, labels: list[str]) -> str:
    """문항·선택지 라벨, 회차·제품군 이름, 문항 코드는 숫자 비교에서 뺀다."""
    for label in sorted({x for x in labels if x}, key=len, reverse=True):
        sentence = sentence.replace(label, " ")
    return _CODE.sub(" ", sentence)


def _matches(token: str, values: list[float]) -> bool:
    decimals = len(token.split(".")[1]) if "." in token else 0
    target = Decimal(token)
    for value in values:
        exact = Decimal(str(value))
        if decimals > 2:
            if exact == target:
                return True
            continue
        if exact.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP) == target:
            return True
    return False




def numbers_match(sentence: str, rows: list[dict], family: str, round_label: str) -> bool:
    labels = [family, round_label]
    values: list[float] = []
    for row in rows:
        labels.extend(part.strip() for part in row["item"].split(" — "))
        values.extend(v for v in row["metrics"].values() if isinstance(v, (int, float)) and not isinstance(v, bool))
    cleaned = _strip_labels(sentence, labels)
    return all(_matches(token, values) for token in _numbers_in(cleaned))


def evaluate_sentence(
    item: dict, rows_by_id: dict[str, dict], allowed_evidence: dict, family: str, round_label: str
) -> tuple[str | None, str | None]:
    """(제외 범주, 제외 사유 코드)를 돌려준다. 통과하면 (None, None). 사유 코드는 dropped_other일 때만 있다."""
    sentence = item["sentence"].strip()
    row_ids = item["row_ids"]
    # (3) row_ids가 입력 표에 있고 하나 이상이다 / (5) 근거 합집합이 비어 있으면 뺀다 (FR-2.4)
    if not row_ids or any(row_id not in rows_by_id for row_id in row_ids):
        return DROPPED_NO_EVIDENCE, None
    if not any(allowed_evidence.get(row_id, {}).get("ids") for row_id in row_ids):
        return DROPPED_NO_EVIDENCE, None
    if not sentence:
        return DROPPED_OTHER, REASON_EMPTY
    if len(sentence) > MAX_SENTENCE_CHARS:
        return DROPPED_OTHER, REASON_TOO_LONG
    if "\n" in sentence or len(_SENTENCE_END.findall(sentence)) > 1:
        return DROPPED_OTHER, REASON_MULTI_SENTENCE
    rows = [rows_by_id[row_id] for row_id in dict.fromkeys(row_ids)]
    # (4) 문장 속 숫자가 참조한 행의 값과 일치한다 (FR-0.3). 한글 수량 표현은 비교할 수 없으므로 제외한다.
    labels = [family, round_label] + [part.strip() for row in rows for part in row["item"].split(" — ")]
    cleaned = _strip_labels(sentence, labels)
    if has_korean_quantity(cleaned):
        return DROPPED_NUMBER_MISMATCH, None
    if not numbers_match(sentence, rows, family, round_label):
        return DROPPED_NUMBER_MISMATCH, None
    if _CHANGE_AFTER_NUMBER.search(cleaned):
        return DROPPED_OTHER, REASON_CHANGE_AFTER_NUMBER
    if _CAUSAL.search(cleaned):
        return DROPPED_OTHER, REASON_CAUSAL_CONNECTOR
    if _CAUSAL_AFTER_NUMBER.search(cleaned):
        return DROPPED_OTHER, REASON_CAUSAL_AFTER_NUMBER
    if any(row["source"] == SYNTHETIC_WORD for row in rows) and SYNTHETIC_WORD not in sentence:
        return DROPPED_OTHER, REASON_MISSING_SYNTHETIC
    if any(row.get("small_sample") for row in rows) and SMALL_SAMPLE_WORD not in sentence:
        return DROPPED_OTHER, REASON_MISSING_SAMPLE
    return None, None


def check_sentence(
    item: dict, rows_by_id: dict[str, dict], allowed_evidence: dict, family: str, round_label: str
) -> str | None:
    """통과하면 None, 제외하면 범주 코드를 돌려준다(사유 코드는 evaluate_sentence)."""
    return evaluate_sentence(item, rows_by_id, allowed_evidence, family, round_label)[0]


@dataclass
class FilterResult:
    accepted: list[dict] = field(default_factory=list)  # {"sentence", "row_ids"} 중복 row_id 제거
    counters: dict = field(
        default_factory=lambda: {
            "proposed": 0,
            "accepted": 0,
            "dropped_no_evidence": 0,
            "dropped_number_mismatch": 0,
            "dropped_other": 0,
        }
    )
    dropped_reasons: dict = field(default_factory=dict)  # dropped_other의 사유 코드별 건수


def filter_suggestions(
    items: list[dict], rows_by_id: dict[str, dict], allowed_evidence: dict, family: str, round_label: str
) -> FilterResult:
    """문장별로 검증한다. 같은 문장은 한 번만 쓰고, 통과한 문장이 5개를 넘으면 뒤의 것은 dropped_other로 센다."""
    result = FilterResult()
    seen: set[str] = set()
    for item in items:
        result.counters["proposed"] += 1
        reason, detail = evaluate_sentence(item, rows_by_id, allowed_evidence, family, round_label)
        if reason is None:
            sentence = item["sentence"].strip()
            if sentence in seen or len(result.accepted) >= MAX_SENTENCES:
                reason = DROPPED_OTHER
                detail = REASON_DUPLICATE if sentence in seen else REASON_OVER_LIMIT
            else:
                seen.add(sentence)
                result.accepted.append({"sentence": sentence, "row_ids": list(dict.fromkeys(item["row_ids"]))})
                result.counters["accepted"] += 1
                continue
        result.counters[reason] += 1
        if reason == DROPPED_OTHER and detail:
            result.dropped_reasons[detail] = result.dropped_reasons.get(detail, 0) + 1
    return result
