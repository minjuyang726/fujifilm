"""호출 B 출력 검증(spec.md 6.3절 호출 B). 문장별로 검증하고, 통과하지 못한 문장은 쓰지 않는다.

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

from app.llm.prompts.suggestion import MAX_SENTENCE_CHARS, MAX_SENTENCES

NOT_JSON = "not_json"
BAD_SCHEMA = "bad_schema"

DROPPED_NO_EVIDENCE = "dropped_no_evidence"
DROPPED_NUMBER_MISMATCH = "dropped_number_mismatch"
DROPPED_OTHER = "dropped_other"

SYNTHETIC_WORD = "합성"
SMALL_SAMPLE_WORD = "표본"

# 한글 수량 표현(FR-0.3: 서술 속 수치는 표의 값과 일치해야 하는데, 아라비아 숫자 검사만으로는 한글로 쓴 수량을 잡지 못한다).
# 표현 목록은 사용자가 정했다(결정 2026-11-03): (1) 절반, 반절, 과반, 곱절, 몇 배, (2) 고유어 수 + 단위
# (한|두|세|네|다섯|여섯|일곱|여덟|아홉|열 + 건|명|점|개|배|문항|가지), (3) 한자어 수 + 단위
# (일|이|삼|사|오|육|칠|팔|구|십|백|천|만 + 건|명|점|개|배|문항|퍼센트).
# 단위가 다른 단어의 일부일 때(만족한 건수, 점수, 개선, 배송)는 잡지 않도록 수 앞에는 한글이 없어야 하고
# 단위 뒤에는 한글이 없거나 조사가 와야 한다. "대부분", "소수", "일부" 같은 질적 표현은 막지 않는다(수치가 아니다).
# 알려진 한계: 지시어 "이"(이 점, 이 건)처럼 한자어 수와 같은 글자가 쓰인 정상 문장도 제외될 수 있다(사용자 목록을 그대로 따름).
_QUANTITY_WORDS = re.compile(r"절반|반절|과반|곱절|몇\s*배")
# 고유어 수: 사용자 목록(한~열)에 더해 열한~열아홉, 스물 이상(스무, 스물, 서른, 마흔, 쉰, 예순, 일흔, 여든, 아흔)도 같은 종류라 포함한다.
_NATIVE_NUMBER = r"(?:(?:스무|스물|서른|마흔|쉰|예순|일흔|여든|아흔|열)?(?:다섯|여섯|일곱|여덟|아홉|한|두|세|네)|열|스무|스물|서른|마흔|쉰|예순|일흔|여든|아흔)"
_SINO_NUMBER = r"(?:일|이|삼|사|오|육|칠|팔|구|십|백|천|만)+"  # 이십, 삼백 같은 합성 수도 잡는다
_AFTER_UNIT = r"(?:(?![가-힣])|(?=[이가을를은는의도만씩으과와에인다로라였입]))"
_NATIVE_QUANTITY = re.compile(rf"(?<![가-힣]){_NATIVE_NUMBER}\s*(?:문항|가지|건|명|점|개|배){_AFTER_UNIT}")
_SINO_QUANTITY = re.compile(rf"(?<![가-힣]){_SINO_NUMBER}\s*(?:문항|퍼센트|건|명|점|개|배){_AFTER_UNIT}")

# 변화·인과 표현(suggest-v3, 결정 2026-11-03). 표(스냅샷)에는 한 시점의 집계 값만 있고 시간에 따른 변화 값이나 원인 정보가 없다.
# (1) 숫자 바로 뒤(단위 % 건 명 점 개 배 포인트 허용)에 개선|증가|감소|확대|축소|향상|상승|하락|인상|인하가 오면
#     응답 비율(예: 개선점으로 고른 33%)을 "33% 개선"처럼 달성 목표나 변화 폭으로 읽게 하거나 표에 없는 비교를 만든다.
# (2) 이므로|때문에|따라서|그래서|덕분에는 표에 없는 인과를 단정한다. 관찰과 제안은 따로 쓰게 한다.
# 두 경우 모두 값이 표와 일치해도 문장의 뜻이 표에 없는 내용을 만든다. 문항·선택지 라벨 속 글자(예: "개선할 점 없음")는 검사에서 뺀다.
_CHANGE_AFTER_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|건|명|점|개|배|포인트)?\s*(?:개선|증가|감소|확대|축소|향상|상승|하락|인상|인하)")
_CAUSAL = re.compile(r"므로|때문에|따라서|그래서|덕분에")  # 므로: 이므로(사용자 목록)에 더해 했으므로, 하므로도 같은 인과 연결이라 포함했다

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3})")
_CODE = re.compile(r"[qQ]\d+")
_SENTENCE_END = re.compile(r"[.!?。](?:\s+|$)")


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


def has_korean_quantity(sentence: str) -> bool:
    """문장에 한글 수량 표현이 있으면 참. 라벨(문항·선택지 이름 등)에 든 글자는 미리 뺀 문장을 넘긴다."""
    return bool(_QUANTITY_WORDS.search(sentence) or _NATIVE_QUANTITY.search(sentence) or _SINO_QUANTITY.search(sentence))


def numbers_match(sentence: str, rows: list[dict], family: str, round_label: str) -> bool:
    labels = [family, round_label]
    values: list[float] = []
    for row in rows:
        labels.extend(part.strip() for part in row["item"].split(" — "))
        values.extend(v for v in row["metrics"].values() if isinstance(v, (int, float)) and not isinstance(v, bool))
    cleaned = _strip_labels(sentence, labels)
    return all(_matches(token, values) for token in _numbers_in(cleaned))


def check_sentence(
    item: dict, rows_by_id: dict[str, dict], allowed_evidence: dict, family: str, round_label: str
) -> str | None:
    """통과하면 None, 제외하면 사유 코드를 돌려준다."""
    sentence = item["sentence"].strip()
    row_ids = item["row_ids"]
    # (3) row_ids가 입력 표에 있고 하나 이상이다 / (5) 근거 합집합이 비어 있으면 뺀다 (FR-2.4)
    if not row_ids or any(row_id not in rows_by_id for row_id in row_ids):
        return DROPPED_NO_EVIDENCE
    if not any(allowed_evidence.get(row_id, {}).get("ids") for row_id in row_ids):
        return DROPPED_NO_EVIDENCE
    if not sentence or len(sentence) > MAX_SENTENCE_CHARS or "\n" in sentence or len(_SENTENCE_END.findall(sentence)) > 1:
        return DROPPED_OTHER
    rows = [rows_by_id[row_id] for row_id in dict.fromkeys(row_ids)]
    # (4) 문장 속 숫자가 참조한 행의 값과 일치한다 (FR-0.3). 한글 수량 표현은 비교할 수 없으므로 제외한다.
    labels = [family, round_label] + [part.strip() for row in rows for part in row["item"].split(" — ")]
    if has_korean_quantity(_strip_labels(sentence, labels)):
        return DROPPED_NUMBER_MISMATCH
    if not numbers_match(sentence, rows, family, round_label):
        return DROPPED_NUMBER_MISMATCH
    if _CHANGE_AFTER_NUMBER.search(_strip_labels(sentence, labels)) or _CAUSAL.search(_strip_labels(sentence, labels)):
        return DROPPED_OTHER
    if any(row["source"] == SYNTHETIC_WORD for row in rows) and SYNTHETIC_WORD not in sentence:
        return DROPPED_OTHER
    if any(row.get("small_sample") for row in rows) and SMALL_SAMPLE_WORD not in sentence:
        return DROPPED_OTHER
    return None


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


def filter_suggestions(
    items: list[dict], rows_by_id: dict[str, dict], allowed_evidence: dict, family: str, round_label: str
) -> FilterResult:
    """문장별로 검증한다. 같은 문장은 한 번만 쓰고, 통과한 문장이 5개를 넘으면 뒤의 것은 dropped_other로 센다."""
    result = FilterResult()
    seen: set[str] = set()
    for item in items:
        result.counters["proposed"] += 1
        reason = check_sentence(item, rows_by_id, allowed_evidence, family, round_label)
        if reason is None:
            sentence = item["sentence"].strip()
            if sentence in seen or len(result.accepted) >= MAX_SENTENCES:
                reason = DROPPED_OTHER
            else:
                seen.add(sentence)
                result.accepted.append({"sentence": sentence, "row_ids": list(dict.fromkeys(item["row_ids"]))})
                result.counters["accepted"] += 1
                continue
        result.counters[reason] += 1
    return result
