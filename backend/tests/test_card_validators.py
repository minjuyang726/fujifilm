"""호출 B(suggest-v4) 출력 검증: 파싱, 카드별 제외 사유, 영역 누락, 공동 순위 라벨. 모든 값은 가짜다."""

import json

import pytest

from app.llm.card_validators import (
    ParsedCards, check_card, filter_cards, parse_cards,
)
from app.llm.suggestion_validators import BAD_SCHEMA, DROPPED_NO_EVIDENCE, DROPPED_NUMBER_MISMATCH, DROPPED_OTHER, NOT_JSON
from app.services.action_cards import Area

GOOD_SENTENCE = "이 영역을 개선 희망으로 고른 응답자는 {pct}이며 {rank}입니다."
GOOD_TEXT = "Q. 처리 기간은 어떻게 되나요? / A. 처리 기간은 [확인 필요: 현재 안내 중인 처리 기간]입니다."


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
    assert check(card(kind="고객 안내 문구 초안", text="가" * 300)) == (None, None)  # 산출물 상한은 300자(suggest-v4의 200자에서 늘렸다)
    assert check(card(kind="고객 안내 문구 초안", text="가" * 301)) == (DROPPED_OTHER, "deliverable_too_long")
    assert check(card(kind="고객 안내 문구 초안", text="가" * 250)) == (None, None)  # 이전 상한(200자)을 넘는 길이도 이제 통과한다


@pytest.mark.parametrize("text", ["안내 후 이용이 늘어나도록 합니다.", "효과를 기대합니다.", "문의가 감소합니다.", "대기가 해소됩니다.", "비용이 줄어듭니다.", "그래서 안내합니다."])
def test_deliverable_with_change_effect_or_causal_expressions_is_dropped(text):
    assert check(card(text=text)) == (DROPPED_OTHER, "deliverable_change_or_cause")


def test_deliverable_may_use_the_confirmation_marker_and_the_word_improvement():
    assert check(card(kind="내부 점검 항목표", text="개선 사항은 [확인 필요]로 표시하고 항목마다 담당을 적습니다.")) == (None, None)
    assert check(card(kind="내부 점검 항목표", text="처리 기간은 [확인 필요: 현재 안내 중인 처리 기간]입니다.")) == (None, None)


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


# ---------- suggest-v5: 산출물은 그대로 쓸 수 있는 초안 문구 ----------
NOTICE_KIND = "고객 안내 문구 초안"


@pytest.mark.parametrize("text", [
    "고객에게 안내되는 예상 기간은 곧 알려 드립니다.",
    "예상 기간 안에 처리됩니다.",
    "예상 처리 기간을 안내해 드립니다.",
    "소요 기간은 문의 후에 안내합니다.",
    "실제 결제 금액이 일치하는지 확인해 드립니다.",
    "결제 금액이 일치하면 접수가 완료됩니다.",
    "재고가 있는 상품만 안내합니다.",
    "판매 단위는 한 세트입니다.",
])
def test_phrases_that_assume_operational_facts_are_dropped(text):
    assert check(card(kind=NOTICE_KIND, text=text)) == (DROPPED_OTHER, "deliverable_operational_fact")


def test_the_same_phrases_are_allowed_inside_a_confirmation_slot():
    assert check(card(kind=NOTICE_KIND, text="처리 기간은 [확인 필요: 현재 안내 중인 예상 기간]입니다.")) == (None, None)
    assert check(card(kind=NOTICE_KIND, text="결제 내용은 [확인 필요: 실제 결제 금액이 일치하는지 확인하는 방법]에 따라 안내합니다.")) == (None, None)
    assert check(card(kind=NOTICE_KIND, text="구성은 [확인 필요: 판매 단위와 재고 상태]를 확인한 뒤 안내합니다.")) == (None, None)
    # 칸 밖에 같은 표현이 하나라도 남으면 거부한다
    assert check(card(kind=NOTICE_KIND, text="재고는 [확인 필요: 재고 현황]이고 재고가 있습니다.")) == (DROPPED_OTHER, "deliverable_operational_fact")


def test_numbers_are_still_dropped_even_inside_a_confirmation_slot():
    assert check(card(kind=NOTICE_KIND, text="처리 기간은 [확인 필요: 3일 이내인지]입니다.")) == (DROPPED_NUMBER_MISMATCH, None)
    assert check(card(kind=NOTICE_KIND, text="처리 기간은 [확인 필요: 현재 비율 %]입니다.")) == (DROPPED_NUMBER_MISMATCH, None)


def test_everyday_words_that_contain_change_words_are_not_blocked():
    # "확인하"에는 "인하"가 들어 있다. 초안은 "확인"을 자주 쓰므로 막지 않는다.
    assert check(card(kind=NOTICE_KIND, text="접수 내용을 확인하겠습니다. 확인하신 뒤 문의해 주십시오.")) == (None, None)


def test_change_cause_and_effect_rules_stay():
    assert check(card(kind=NOTICE_KIND, text="안내를 개선하면 문의가 줄어듭니다.")) == (DROPPED_OTHER, "deliverable_change_or_cause")
    assert check(card(kind=NOTICE_KIND, text="따라서 안내를 드립니다.")) == (DROPPED_OTHER, "deliverable_change_or_cause")


def test_faq_drafts_need_a_question_and_an_answer():
    assert check(card(kind="FAQ 초안", text="Q. 처리 기간은 어떻게 되나요? / A. [확인 필요: 현재 안내 중인 처리 기간]입니다.")) == (None, None)
    assert check(card(kind="FAQ 초안", text="자주 묻는 질문과 답변을 정리해야 합니다.")) == (DROPPED_OTHER, "faq_format")
    assert check(card(kind="FAQ 초안", text="Q. 처리 기간은 어떻게 되나요?")) == (DROPPED_OTHER, "faq_format")
    assert check(card(kind="FAQ 초안", text="A. 확인 후 안내합니다.")) == (DROPPED_OTHER, "faq_format")
    assert check(card(kind="FAQ 초안", text="FAQ. 문답을 정리했습니다.")) == (DROPPED_OTHER, "faq_format")  # FAQ의 Q., A.는 문답 표시가 아니다
    assert check(card(kind=NOTICE_KIND, text="질문과 답변 형식이 아니어도 됩니다.")) == (None, None)  # 다른 종류에는 적용하지 않는다


def test_the_operational_fact_list_is_documented_in_code():
    from app.llm import card_validators

    assert len(card_validators.OPERATIONAL_FACT_PATTERNS) >= 7
    source = open(card_validators.__file__, encoding="utf-8").read()
    assert "근거:" in source and "안내되는 예상 기간" in source  # 목록에 넣은 근거를 주석으로 남겼다
