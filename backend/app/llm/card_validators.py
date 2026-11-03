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
from app.services.action_cards import Area, fill_placeholders

# ---- 호출 B·C 검증기가 함께 쓰는 정의 (suggest-v3 검증기에서 옮겨 왔다) ----
NOT_JSON = "not_json"
BAD_SCHEMA = "bad_schema"

DROPPED_NO_EVIDENCE = "dropped_no_evidence"
DROPPED_NUMBER_MISMATCH = "dropped_number_mismatch"
DROPPED_OTHER = "dropped_other"

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
# 숫자·단위 바로 뒤의 "여서/이어서/이라서/라서"도 같은 인과 연결이다(결정 2026-11-03). 근거: suggest-v3 통과 문장 16개 중 3개가
# "37%여서", "71.4%여서", "100%여서"처럼 숫자 뒤에 이 연결을 썼다. 라벨 속 글자는 검사에서 뺀다. 일반 명사 뒤의 "~라서"까지 막지 않도록
# 숫자(와 단위) 바로 뒤일 때만 잡는다.
_CAUSAL_AFTER_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|건|명|점|개|배|포인트)?\s*(?:이어서|이라서|여서|라서)")
_CAUSAL = re.compile(r"므로|때문에|따라서|그래서|덕분에")  # 므로: 이므로(사용자 목록)에 더해 했으므로, 하므로도 같은 인과 연결이라 포함했다


_SENTENCE_END = re.compile(r"[.!?。](?:\s+|$)")


def has_korean_quantity(sentence: str) -> bool:
    """문장에 한글 수량 표현이 있으면 참. 라벨(문항·선택지 이름 등)에 든 글자는 미리 뺀 문장을 넘긴다."""
    return bool(_QUANTITY_WORDS.search(sentence) or _NATIVE_QUANTITY.search(sentence) or _SINO_QUANTITY.search(sentence))


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
REASON_DELIVERABLE_OPERATIONAL_FACT = "deliverable_operational_fact"
REASON_FAQ_FORMAT = "faq_format"

_DIGIT = re.compile(r"\d")
# 산출물 본문의 변화·효과 표현. 숫자가 없는 글이라 "숫자 바로 뒤" 규칙(_CHANGE_AFTER_NUMBER)은 걸리지 않으므로 단어 자체를 막는다.
# 영역 이름 속 글자(예: 개선)는 막지 않으려고 "개선"은 목록에서 뺀다. "인상"·"인하"는 "확인하"·"좋은 인상"처럼 흔한 말에 들어 있어서 뺀다(v5 초안은 "확인"을 자주 쓴다).
_CHANGE_OR_EFFECT = re.compile(r"증가|감소|확대|축소|향상|상승|하락|효과|해소|줄어|늘어|높아|낮아")
_BRACE = re.compile(r"[{}]")

# "[확인 필요: 확인할 내용]" 칸. 운영 사실이 들어갈 자리를 비워 두는 표시이고, 칸 안의 글은 운영 사실 검사에서 뺀다.
# 칸 안에도 숫자는 쓸 수 없다(숫자·% 검사는 본문 전체에 적용한다). "[확인 필요]"만 쓴 칸도 허용한다.
CONFIRMATION_SLOT = re.compile(r"\[확인 필요(?::[^\]\n]*)?\]")

# 운영 사실을 전제하는 표현. 에이전트는 현재 운영의 기간·결제·재고·판매 단위를 알 수 없으므로 초안이 이를 단정하면 안 된다.
# 근거: suggest-v4 산출물을 검토한 사용자의 지적(2026-11-03)에서 나온 유형이다 - "안내되는 예상 기간", "실제 결제 금액이 일치", "재고·판매 단위".
# 각 표현은 칸 밖에서 쓰이면 사실을 단정하는 문구가 된다. 목록은 완전하지 않으며(다른 운영 사실 표현은 프롬프트로만 막는다) 새 유형이 나오면 여기에 더한다.
# suggest-v6에서 "현재 …"형 전제 표현을 더했다. 근거: 리포트 #12~#15를 읽은 사용자의 지적(2026-11-03) - "현재 안내 중인", "현재 적용 중인"처럼 안내·적용·제공·운영이
# 현재 있다는 전제를 칸 밖 문장에 까는 표현이 남았다. 내용(기간, 금액)뿐 아니라 있는지 자체를 단정하지 않으려는 규칙이다. 칸 안에서는 쓸 수 있다.
# 일부러 넣지 않은 것: 영역 이름에서 나온 서비스 단어(현상, 인화, 처리 기간, 서비스 이용). 영역 이름을 그대로 인용하는 정상 문장과 "처리 기간은 [확인 필요: …]입니다" 같은
# 프롬프트가 권하는 문장을 함께 막고(오탐), 코드는 인용과 서비스 단정을 구별하지 못한다. 이 경우는 프롬프트 규칙으로만 막는다.
OPERATIONAL_FACT_PATTERNS = (
    re.compile(r"현재\s*(?:안내|적용|제공|운영)\s*(?:중|하는|하고|되는|되고|되어)"),
    re.compile(r"안내되는\s*예상\s*기간"),
    re.compile(r"예상\s*(?:처리\s*)?기간"),
    re.compile(r"소요\s*(?:되는\s*)?기간"),
    re.compile(r"실제\s*결제\s*금액"),
    re.compile(r"결제\s*금액이\s*일치"),
    re.compile(r"재고"),
    re.compile(r"판매\s*단위"),
)
FAQ_KIND = "FAQ 초안"
_FAQ_QUESTION = re.compile(r"(?<![A-Za-z])Q\.")  # "FAQ."의 Q.는 문답 표시가 아니다
_FAQ_ANSWER = re.compile(r"(?<![A-Za-z])A\.")


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
    outside_slots = CONFIRMATION_SLOT.sub(" ", deliverable)
    if any(pattern.search(outside_slots) for pattern in OPERATIONAL_FACT_PATTERNS):
        return DROPPED_OTHER, REASON_DELIVERABLE_OPERATIONAL_FACT
    if item["deliverable_kind"] == FAQ_KIND and not (_FAQ_QUESTION.search(deliverable) and _FAQ_ANSWER.search(deliverable)):
        return DROPPED_OTHER, REASON_FAQ_FORMAT
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
