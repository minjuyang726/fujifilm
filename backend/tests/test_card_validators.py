"""호출 B(suggest-v4) 출력 검증: 파싱, 카드별 제외 사유, 영역 누락, 공동 순위 라벨. 모든 값은 가짜다."""

import json

import pytest

from app.llm.card_validators import (
    ParsedCards, check_card, filter_cards, parse_cards,
)
from app.llm.suggestion_validators import BAD_SCHEMA, DROPPED_NO_EVIDENCE, DROPPED_NUMBER_MISMATCH, DROPPED_OTHER, NOT_JSON
from app.services.action_cards import Area

GOOD_SENTENCE = "이 영역을 개선 희망으로 고른 응답자는 {pct}이며 {rank}입니다."
GOOD_TEXT = "자주 묻는 질문과 답변 초안입니다. 기간과 비용은 [확인 필요]입니다."


def area(code, label, rank, rank_label, joint=False, pct=33.0):
    return Area(code=code, label=label, count=int(pct), pct=pct, rank=rank, rank_label=rank_label, joint=joint,
                row_ids=[f"survey:q08:{code}"])


AREAS = [area("1", "필름·소모품 비용", 1, "공동 1순위", True, 33.0), area("4", "결과물 품질", 2, "2순위", False, 26.0), area("2", "현상·인화 대기", 3, "3순위", False, 25.0)]
BY_CODE = {a.code: a for a in AREAS}


def card(code="1", sentence=GOOD_SENTENCE, kind="FAQ 초안", text=GOOD_TEXT):
    return {"area_code": code, "priority_sentence": sentence, "deliverable_kind": kind, "deliverable_text": text}


def check(item, accepted=()):
    return check_card(item, BY_CODE, set(accepted))


# ---------- 파싱 ----------
def test_parse_rejects_non_json_and_bad_schema():
    assert parse_cards(None).problem == NOT_JSON
    assert parse_cards("not json").problem == NOT_JSON
    assert parse_cards('{"other": []}').problem == BAD_SCHEMA
    assert parse_cards('{"cards": [{"area_code": 1}]}').problem == BAD_SCHEMA
    extra = {**card(), "extra": "x"}
    assert parse_cards(json.dumps({"cards": [extra]})).problem == BAD_SCHEMA
    missing = {k: v for k, v in card().items() if k != "deliverable_text"}
    assert parse_cards(json.dumps({"cards": [missing]})).problem == BAD_SCHEMA
    ok = parse_cards(json.dumps({"cards": [card()]}))
    assert ok.problem is None and ok.items == [card()]


# ---------- 통과 ----------
def test_a_good_card_passes():
    assert check(card()) == (None, None)
    assert check(card("4")) == (None, None)  # 공동이 아닌 영역: {rank}가 "2순위"로 채워진다


# ---------- 영역 코드 ----------
def test_unknown_area_code_is_dropped_as_no_evidence():
    assert check(card("9")) == (DROPPED_NO_EVIDENCE, None)
    assert check(card("5")) == (DROPPED_NO_EVIDENCE, None)  # 개선할 점 없음은 영역이 아니다


def test_duplicate_area_code_is_dropped_as_other():
    assert check(card("1"), accepted={"1"}) == (DROPPED_OTHER, "duplicate_area")


# ---------- 숫자와 자리표시자 ----------
@pytest.mark.parametrize("sentence", [
    "이 영역을 고른 응답자는 33.0%이며 {rank}입니다. {pct}",
    "이 영역을 고른 응답자는 {pct}이며 {rank}이고 33명입니다.",
    "이 영역은 {pct}이며 {rank}이고 1위입니다.",
])
def test_digits_in_the_priority_sentence_are_dropped_as_number_mismatch(sentence):
    assert check(card(sentence=sentence)) == (DROPPED_NUMBER_MISMATCH, None)


def test_percent_sign_written_by_the_model_is_dropped_as_number_mismatch():
    assert check(card(sentence="이 영역은 {pct}%이며 {rank}입니다.")) == (DROPPED_NUMBER_MISMATCH, None)


def test_digits_percent_in_the_deliverable_are_dropped_as_number_mismatch():
    assert check(card(text="문의는 3일 안에 답변합니다.")) == (DROPPED_NUMBER_MISMATCH, None)
    assert check(card(text="문의 비중이 높습니다 %")) == (DROPPED_NUMBER_MISMATCH, None)
    assert check(card(text="문의 비중이 높습니다 ％")) == (DROPPED_NUMBER_MISMATCH, None)


def test_pct_placeholder_must_appear_exactly_once():
    assert check(card(sentence="이 영역을 고른 응답자가 많고 {rank}입니다.")) == (DROPPED_NUMBER_MISMATCH, None)
    assert check(card(sentence="이 영역은 {pct} 또는 {pct}이며 {rank}입니다.")) == (DROPPED_NUMBER_MISMATCH, None)


def test_rank_placeholder_must_appear_exactly_once_and_no_other_braces():
    assert check(card(sentence="이 영역은 {pct}입니다.")) == (DROPPED_OTHER, "bad_placeholder")
    assert check(card(sentence="이 영역은 {pct}이며 {rank} 그리고 {rank}입니다.")) == (DROPPED_OTHER, "bad_placeholder")
    assert check(card(sentence="이 영역은 {pct}이며 {rank} {other}입니다.")) == (DROPPED_OTHER, "bad_placeholder")


def test_korean_quantity_words_are_dropped_as_number_mismatch():
    assert check(card(sentence="이 영역은 {pct}이며 {rank}이고 절반에 가깝습니다.")) == (DROPPED_NUMBER_MISMATCH, None)
    assert check(card(text="답변은 두 건 이내로 안내합니다.")) == (DROPPED_NUMBER_MISMATCH, None)


# ---------- 공동 순위 라벨 ----------
def test_joint_word_written_by_the_model_is_dropped_because_the_code_fills_the_rank_label():
    assert check(card("1", sentence="이 영역은 {pct}이며 공동 {rank}입니다.")) == (DROPPED_OTHER, "rank_label_mismatch")  # 공동 + 공동 1순위
    assert check(card("4", sentence="이 영역은 {pct}이며 공동으로 {rank}입니다.")) == (DROPPED_OTHER, "rank_label_mismatch")  # 공동이 아닌 영역


def test_joint_area_without_the_rank_placeholder_is_dropped():
    # 공동 순위인데 {rank} 없이 쓰면 공동 표기가 빠진다
    assert check(card("1", sentence="이 영역은 {pct}입니다.")) == (DROPPED_OTHER, "bad_placeholder")


def test_filled_sentence_has_joint_exactly_for_joint_areas():
    from app.services.action_cards import fill_placeholders
    assert "공동" in fill_placeholders(GOOD_SENTENCE, BY_CODE["1"]) and "공동" not in fill_placeholders(GOOD_SENTENCE, BY_CODE["4"])


# ---------- 변화·인과·길이·문장 수 (값을 채운 뒤 문장에 적용) ----------
def test_change_expression_right_after_the_filled_value_is_dropped():
    assert check(card(sentence="이 영역은 {pct} 개선이며 {rank}입니다.")) == (DROPPED_OTHER, "change_after_number")
    assert check(card(sentence="이 영역은 {pct} 증가했고 {rank}입니다.")) == (DROPPED_OTHER, "change_after_number")


def test_causal_connectors_are_dropped():
    assert check(card(sentence="이 영역은 {pct}이므로 {rank}입니다.")) == (DROPPED_OTHER, "causal_connector")
    assert check(card(sentence="이 영역은 {pct}여서 {rank}입니다.")) == (DROPPED_OTHER, "causal_after_number")
    assert check(card(sentence="따라서 이 영역은 {pct}이며 {rank}입니다.")) == (DROPPED_OTHER, "causal_connector")


def test_length_is_checked_after_filling_and_one_sentence_only():
    # 공동 1순위 영역: 채운 값 "33.0%"(5자)와 "공동 1순위"(6자)가 들어가 글자 수가 늘어난다
    at_limit = "가" * 109 + "{pct}{rank}"
    assert len(fill(at_limit)) == 120 and check(card(sentence=at_limit)) == (None, None)
    over = "가" * 110 + "{pct}{rank}"
    assert len(fill(over)) == 121 and check(card(sentence=over)) == (DROPPED_OTHER, "too_long")
    assert check(card(sentence="이 영역은 {pct}입니다. 또 {rank}입니다.")) == (DROPPED_OTHER, "multi_sentence")
    assert check(card(sentence="   ")) == (DROPPED_OTHER, "empty")


def fill(sentence):
    from app.services.action_cards import fill_placeholders
    return fill_placeholders(sentence, BY_CODE["1"])


def test_the_value_with_a_decimal_point_is_not_a_sentence_end():
    assert check(card()) == (None, None)  # 채운 문장의 "33.0%"의 소수점은 문장 끝이 아니다


# ---------- 산출물 ----------
def test_deliverable_kind_must_be_in_the_fixed_list():
    assert check(card(kind="보고서")) == (DROPPED_OTHER, "bad_deliverable_kind")
    for kind in ("고객 안내 문구 초안", "FAQ 초안", "내부 점검 항목표", "내부 보고 문단"):
        assert check(card(kind=kind)) == (None, None)


def test_deliverable_text_length_and_empty():
    assert check(card(text="  ")) == (DROPPED_OTHER, "deliverable_empty")
    assert check(card(text="가" * 200)) == (None, None)
    assert check(card(text="가" * 201)) == (DROPPED_OTHER, "deliverable_too_long")


@pytest.mark.parametrize("text", ["안내 후 이용이 늘어나도록 합니다.", "효과를 기대합니다.", "문의가 감소합니다.", "대기가 해소됩니다.", "비용이 줄어듭니다.", "그래서 안내합니다."])
def test_deliverable_with_change_effect_or_causal_expressions_is_dropped(text):
    assert check(card(text=text)) == (DROPPED_OTHER, "deliverable_change_or_cause")


def test_deliverable_may_use_the_confirmation_marker_and_the_word_improvement():
    assert check(card(text="개선 사항은 [확인 필요]로 표시하고 항목마다 담당을 적습니다.")) == (None, None)


# ---------- 필터 ----------
def full_items():
    return [card("1"), card("4"), card("2")]


def test_filter_accepts_all_areas_and_keeps_rank_order():
    result = filter_cards(list(reversed(full_items())), AREAS)
    assert result.complete and [c["area"].code for c in result.accepted] == ["1", "4", "2"]
    assert result.counters == {"proposed": 3, "accepted": 3, "dropped_no_evidence": 0, "dropped_number_mismatch": 0, "dropped_other": 0}
    assert result.dropped_reasons == {}


def test_filter_counts_each_reason_and_missing_areas_are_dropped_other():
    items = [
        card("1"),  # 통과
        card("9"),  # 알 수 없는 area_code
        card("4", sentence="이 영역은 33.0%이며 {rank}입니다."),  # 숫자
        card("1"),  # 중복
    ]
    result = filter_cards(items, AREAS)
    assert not result.complete
    assert result.counters == {"proposed": 4, "accepted": 1, "dropped_no_evidence": 1, "dropped_number_mismatch": 1, "dropped_other": 1 + 2}
    assert result.dropped_reasons == {"duplicate_area": 1, "missing_area": 2}
    assert [c["area"].code for c in result.accepted] == ["1"]


def test_filter_missing_one_area_is_not_complete():
    result = filter_cards([card("1"), card("4")], AREAS)
    assert not result.complete and result.dropped_reasons == {"missing_area": 1}


def test_filter_with_no_areas_is_never_complete():
    assert filter_cards([], []).complete is False
