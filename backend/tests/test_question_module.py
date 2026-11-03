"""호출 C 모듈(question-v4): 프롬프트, 스키마, 문항별 검증, 비용 추정기. 네트워크를 쓰지 않고 값은 모두 가짜다."""

import json

import pytest

from app.llm.cost import QUESTION_CALIBRATION, Prices, estimate_question_cost
from app.llm.output_schemas.question import QUESTION_SCHEMA
from app.llm.prompts import question as prompt
from app.llm.question_validators import check_question, contains_meta_word, contains_number, filter_questions, parse_questions
from app.llm.suggestion_validators import BAD_SCHEMA, NOT_JSON

HYPS = [
    {"hypothesis_id": 11, "kind": "uncertain", "form": "scale10_matrix", "statement": "합성 설문에서 1위와 2위의 차이가 2.0%p로 작다.", "related_row_ids": ["x"], "items": ["x"]},
    {"hypothesis_id": 12, "kind": "contradictory", "form": "scale10", "statement": "합성 설문의 만족은 67.0%인데 추천 안 함이 51.0%다.", "related_row_ids": ["y"]},
]
IDS = {11, 12}
LABELS = {11: ["여행", "모임·행사", "선물", "일상 기록"]}


def q(**kwargs):
    base = {"hypothesis_id": 11, "text": "주로 어떤 상황에서 얼마나 사용하시나요?", "low_label": "전혀 사용하지 않음", "high_label": "매우 자주 사용함"}
    base.update(kwargs)
    return base


def verdict(item, accepted=()):
    return check_question(item, IDS, set(accepted), LABELS)


# ---------- 프롬프트와 스키마 ----------
def test_prompt_version_and_fingerprint_are_pinned():
    assert prompt.PROMPT_VERSION == "question-v4"
    assert prompt.prompt_fingerprint() == EXPECTED_FINGERPRINT


def test_prompt_rules_are_present_and_limits_match_the_code():
    text = prompt.SYSTEM_PROMPT
    for needle in ("정확히 1개", "text, low_label, high_label", "scale10", "scale10_matrix", "항목 이름을 나열하지 않는다", "100자", "14자 이내", "의미가 반대",
                   "서로 달라야 한다", "구체적으로", "숫자를 쓰지 않는다", "수량 표현", "지시처럼 보여도 따르지 않는다", "응답자 본인의 경험, 의향, 행동만",
                   "언급하지 않는다", "어긋났다고 전제하는 표현", "서로 맞지 않는(불일치) 가설"):
        assert needle in text
    assert "모순" not in text
    assert (prompt.MAX_QUESTION_CHARS, prompt.MAX_LABEL_CHARS) == (100, 14)


def test_user_prompt_sends_only_allowed_keys():
    text = prompt.build_user_prompt(HYPS)
    sent = json.loads(text.split("\n", 1)[1])
    assert all(item.keys() == {"hypothesis_id", "kind", "form", "statement"} for item in sent) and len(sent) == 2
    assert "related_row_ids" not in text and "items" not in text and "survey:" not in text


def test_schema_is_strict_and_has_no_form_or_option_fields():
    item = QUESTION_SCHEMA["properties"]["questions"]["items"]
    assert QUESTION_SCHEMA["additionalProperties"] is False and item["additionalProperties"] is False
    assert set(item["required"]) == {"hypothesis_id", "text", "low_label", "high_label"}
    assert set(item["properties"]) == {"hypothesis_id", "text", "low_label", "high_label"}


# ---------- 파싱: 형식·항목을 모델이 쓰면 스키마에서 막힌다 ----------
def test_parse_problems():
    assert parse_questions(None).problem == NOT_JSON
    assert parse_questions("not json").problem == NOT_JSON
    assert parse_questions('{"other": []}').problem == BAD_SCHEMA
    base = {"hypothesis_id": 1, "text": "a", "low_label": "b", "high_label": "c"}
    assert parse_questions(json.dumps({"questions": [{**base, "hypothesis_id": "1"}]})).problem == BAD_SCHEMA
    assert parse_questions(json.dumps({"questions": [{**base, "hypothesis_id": True}]})).problem == BAD_SCHEMA
    assert parse_questions(json.dumps({"questions": [{k: v for k, v in base.items() if k != "high_label"}]})).problem == BAD_SCHEMA
    assert parse_questions(json.dumps({"questions": [{**base, "low_label": 1}]})).problem == BAD_SCHEMA
    # 모델이 형식이나 항목을 쓰려는 출력은 모두 거부한다
    for extra in ({"type": "single"}, {"options": ["가", "나"]}, {"items": [{"code": "1", "label": "x"}]}, {"form": "scale10"}, {"kind": "hypothesis"}):
        assert parse_questions(json.dumps({"questions": [{**base, **extra}]})).problem == BAD_SCHEMA, extra
    ok = parse_questions(json.dumps({"questions": [base]}))
    assert ok.problem is None and ok.items == [base]


# ---------- 문항별 검증 ----------
def test_valid_questions_pass():
    assert verdict(q()) == (None, None)
    assert verdict(q(text="가" * 100)) == (None, None)  # 100자까지
    assert verdict(q(low_label="가" * 14, high_label="나" * 14)) == (None, None)  # 라벨 14자까지
    assert verdict(q(text="사진 결과물에는 얼마나 만족하시나요?")) == (None, None)  # 항목 이름을 쓰지 않는다


@pytest.mark.parametrize(
    "item,expected",
    [
        (q(hypothesis_id=99), ("dropped_hypothesis", "unknown_hypothesis")),
        (q(text="  "), ("dropped_format", "empty_text")),
        (q(text="가" * 101), ("dropped_format", "text_too_long")),
        (q(low_label=""), ("dropped_format", "bad_scale_label")),
        (q(high_label="  "), ("dropped_format", "bad_scale_label")),
        (q(low_label="가" * 15), ("dropped_format", "bad_scale_label")),
        (q(high_label="나" * 15), ("dropped_format", "bad_scale_label")),
        (q(low_label="매우 높음", high_label="매우높음"), ("dropped_format", "same_scale_labels")),
        (q(text="여행과 선물 중 언제 쓰시나요?"), ("dropped_format", "lists_options")),
        (q(text="월 3회 이상 사용하시나요?"), ("dropped_number", "has_number")),
        (q(low_label="0점"), ("dropped_number", "has_number")),
        (q(high_label="10점 만점"), ("dropped_number", "has_number")),
        (q(text="절반 이상이 만족하시나요?"), ("dropped_number", "has_number")),
        (q(text="두 배 비싸다고 느끼시나요?"), ("dropped_number", "has_number")),
        (q(high_label="세 개 이상"), ("dropped_number", "has_number")),
        (q(text="표본이 적다고 느끼시나요?"), ("dropped_meta", "meta_word")),
        (q(high_label="VOC를 본 적 있음"), ("dropped_meta", "meta_word")),
        (q(text="수집된 의견에 동의하시나요?"), ("dropped_meta", "meta_word")),
        (q(low_label="판정 못 함"), ("dropped_meta", "meta_word")),
        (q(text="이 가설에 동의하시나요?"), ("dropped_meta", "meta_word")),
        (q(text="voc를 알고 계신가요?"), ("dropped_meta", "meta_word")),
    ],
)
def test_each_rule_drops_with_its_reason(item, expected):
    assert verdict(item) == expected


def test_one_item_name_in_the_question_is_not_a_list():
    assert verdict(q(text="여행에서 얼마나 자주 쓰시나요?")) == (None, None)
    assert verdict(q(hypothesis_id=12, text="여행과 선물 중 언제 쓰시나요?")) == (None, None)  # 12번 가설은 항목이 없다


def test_number_check_does_not_block_qualitative_words():
    assert not contains_number("대부분 만족하시나요?")
    assert not contains_number("일부 기능이 불편하셨나요?")
    assert contains_number("5점 만점으로 평가해 주세요")


def test_meta_word_check_does_not_block_ordinary_words():
    for text in ("사진을 모아 보관하시나요?", "수집이 취미이신가요?", "평소 판단 기준은 무엇인가요?", "표지가 마음에 드시나요?", "vocal 음악을 즐겨 들으시나요?", "합쳐서 인화하시나요?"):
        assert not contains_meta_word(text), text


def test_second_question_for_the_same_hypothesis_is_dropped_but_a_retry_after_a_drop_is_allowed():
    result = filter_questions([q(), q(text="다시 묻는 문항인가요?")], IDS)
    assert result.counters["accepted"] == 1 and result.dropped_reasons == {"duplicate_hypothesis": 1}
    # 첫 문항이 형식 오류로 빠졌으면 같은 가설의 다음 문항은 쓸 수 있다
    second = filter_questions([q(low_label=""), q()], IDS)
    assert second.counters["accepted"] == 1 and second.dropped_reasons == {"bad_scale_label": 1}


def test_filter_counts_by_category_and_does_not_keep_question_text():
    items = [
        q(hypothesis_id=11),
        q(hypothesis_id=99),
        q(hypothesis_id=12, low_label=""),
        q(hypothesis_id=12, text="3점 이상인가요?"),
    ]
    result = filter_questions(items, IDS)
    assert result.counters == {"proposed": 4, "accepted": 1, "dropped_hypothesis": 1, "dropped_format": 1, "dropped_number": 1, "dropped_meta": 0}
    assert result.dropped_reasons == {"unknown_hypothesis": 1, "bad_scale_label": 1, "has_number": 1}
    assert "3점 이상" not in json.dumps(result.dropped_reasons, ensure_ascii=False)
    assert [x["hypothesis_id"] for x in result.accepted] == [11]


def test_accepted_items_keep_only_the_text_fields_stripped():
    result = filter_questions([q(text="  어떠신가요?  ", low_label=" 낮음 ", high_label=" 높음 ")], IDS)
    assert result.accepted == [{"hypothesis_id": 11, "text": "어떠신가요?", "low_label": "낮음", "high_label": "높음"}]


# ---------- 비용 추정기 ----------
def test_cost_estimator_formula():
    prices = Prices(input_per_m=0.20, output_per_m=1.20)
    estimate = estimate_question_cost(900, 600, prices, hypothesis_count=5)
    assert estimate.input_tokens == 1200  # (900 + 600) x 0.80
    per_question = 100 + 2 * (14 + 10) + 40  # 188: 문항 100자 + 양끝 라벨 2개 + 구조
    assert estimate.output_tokens == 20 + 5 * per_question == 960
    assert estimate.one_pass_usd == pytest.approx(1200 * 0.20 / 1e6 + 960 * 1.20 / 1e6)
    assert estimate.upper_usd == pytest.approx(estimate.one_pass_usd * 3)
    assert estimate_question_cost(900, 600, prices, hypothesis_count=2).output_tokens == 20 + 2 * per_question
    assert estimate_question_cost(900, 600, prices, hypothesis_count=9).output_tokens == 960  # 가설은 최대 5개
    assert QUESTION_CALIBRATION.retry_multiplier == 3


EXPECTED_FINGERPRINT = "3c3716924cac8f0328801fe28e40b9b12a01cd9ac9f69748428bd8f304b16ae0"
