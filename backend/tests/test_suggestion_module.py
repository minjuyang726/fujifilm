"""호출 B 모듈: 프롬프트, 스키마, 문장별 검증, 비용 추정기. 네트워크를 쓰지 않고 값은 모두 가짜다."""

import json

import pytest

from app.llm.cost import Prices, SUGGESTION_CALIBRATION, estimate_suggestion_cost
from app.llm.output_schemas.suggestion import SUGGESTION_SCHEMA
from app.llm.prompts import suggestion as prompt
from app.llm.suggestion_validators import (
    has_korean_quantity, BAD_SCHEMA, DROPPED_NO_EVIDENCE, DROPPED_NUMBER_MISMATCH, DROPPED_OTHER, NOT_JSON,
    check_sentence, filter_suggestions, numbers_match, parse_suggestions,
)

FAMILY, ROUND = "인스탁스 즉석카메라", "2026-Q1"

ROWS = [
    {"row_id": "survey:q09:1", "group": "설문", "source": "합성", "item": "지인에게 추천한 적이 있으신가요? — 예",
     "metrics": {"응답 수": 49, "비율(%)": 49.0, "선택지 번호": 1}, "small_sample": False},
    {"row_id": "survey:q01:5", "group": "설문", "source": "합성", "item": "전반적인 만족도는 어떠셨나요? — 매우 만족",
     "metrics": {"응답 수": 28, "비율(%)": 28.0, "선택지 번호": 5}, "small_sample": False},
    {"row_id": "survey:q10:3", "group": "설문", "source": "합성", "item": "얼마나 자주 사용하셨나요? — 월 1~3회",
     "metrics": {"응답 수": 28, "비율(%)": 28.4, "선택지 번호": 3}, "small_sample": False},
    {"row_id": "voc:total:count", "group": "VOC", "source": "실측", "item": "VOC 전체 리뷰(선택한 제품군·회차)",
     "metrics": {"리뷰 수": 37}, "small_sample": False},
    {"row_id": "voc:judged:mean_weighted", "group": "VOC", "source": "실측", "item": "판정 묶음 가중 평균 평점",
     "metrics": {"가중 평균 평점": 4.8571, "가중치 하한": 0.1}, "small_sample": True},
    {"row_id": "voc:empty", "group": "VOC", "source": "실측", "item": "비어 있는 행", "metrics": {"건수": 0}, "small_sample": False},
]
BY_ID = {r["row_id"]: r for r in ROWS}
EVIDENCE = {
    "survey:q09:1": {"kind": "survey", "ids": [1, 2, 3]},
    "survey:q01:5": {"kind": "survey", "ids": [4]},
    "survey:q10:3": {"kind": "survey", "ids": [5]},
    "voc:total:count": {"kind": "review", "ids": [10, 11]},
    "voc:judged:mean_weighted": {"kind": "review", "ids": [10]},
    "voc:empty": {"kind": "review", "ids": []},
}


def check(sentence, row_ids):
    return check_sentence({"sentence": sentence, "row_ids": row_ids}, BY_ID, EVIDENCE, FAMILY, ROUND)


# ---------- 프롬프트와 스키마 ----------
def test_prompt_version_and_fingerprint_are_pinned():
    assert prompt.PROMPT_VERSION == "suggest-v2"
    # 문구를 바꾸면 이 값과 PROMPT_VERSION을 같이 바꾼다
    assert prompt.prompt_fingerprint() == EXPECTED_FINGERPRINT


def test_prompt_contains_the_required_rules():
    text = prompt.SYSTEM_PROMPT
    for needle in ("아라비아 숫자", "표에 없는 숫자를 만들지 않는다", "합성", "표본", "120자", "최대 5개", "row_ids", "절반, 두 배, 세 건 같은 한글 수량 표현은 쓰지 않는다"):
        assert needle in text
    for forbidden in ("author", "variant"):  # 영어 키 이름은 쓰지 않는다
        assert forbidden not in text


def test_user_prompt_sends_only_allowed_row_keys_and_no_evidence_ids():
    row = {**ROWS[0], "evidence": [1, 2], "author": "x"}
    text = prompt.build_user_prompt(FAMILY, ROUND, [row])
    assert "evidence" not in text and "author" not in text and "row_id" in text and FAMILY in text
    assert json.loads(text.split("\n", 1)[1])["table"][0].keys() == {"row_id", "group", "source", "item", "metrics", "small_sample"}


def test_schema_is_strict():
    item = SUGGESTION_SCHEMA["properties"]["suggestions"]["items"]
    assert SUGGESTION_SCHEMA["additionalProperties"] is False and item["additionalProperties"] is False
    assert set(item["required"]) == {"sentence", "row_ids"}


# ---------- 출력 파싱 ----------
def test_parse_rejects_non_json_and_bad_schema():
    assert parse_suggestions(None).problem == NOT_JSON
    assert parse_suggestions("not json").problem == NOT_JSON
    assert parse_suggestions('{"other": []}').problem == BAD_SCHEMA
    assert parse_suggestions('{"suggestions": [{"sentence": 1, "row_ids": []}]}').problem == BAD_SCHEMA
    assert parse_suggestions('{"suggestions": [{"sentence": "a", "row_ids": [1]}]}').problem == BAD_SCHEMA
    assert parse_suggestions('{"suggestions": [{"sentence": "a", "row_ids": [], "extra": 1}]}').problem == BAD_SCHEMA
    ok = parse_suggestions('{"suggestions": [{"sentence": "a", "row_ids": ["x"]}]}')
    assert ok.problem is None and ok.items == [{"sentence": "a", "row_ids": ["x"]}]


# ---------- 문장별 제외 ----------
def test_a_good_sentence_passes():
    assert check("합성 설문에서 지인에게 추천한 적이 있다는 응답이 49건(49.0%)이라 추천 경로를 넓히는 안을 검토한다.", ["survey:q09:1"]) is None


def test_row_id_errors_are_dropped_as_no_evidence():
    assert check("합성 설문 응답이 49건이다.", ["survey:nope"]) == DROPPED_NO_EVIDENCE
    assert check("합성 설문 응답이 49건이다.", []) == DROPPED_NO_EVIDENCE
    assert check("합성 설문 응답이 49건이다.", ["survey:q09:1", "survey:nope"]) == DROPPED_NO_EVIDENCE


def test_empty_evidence_union_is_dropped_as_no_evidence():
    assert check("건수는 0건이다.", ["voc:empty"]) == DROPPED_NO_EVIDENCE


def test_number_mismatch_is_dropped():
    assert check("합성 설문에서 추천 응답이 50건이다.", ["survey:q09:1"]) == DROPPED_NUMBER_MISMATCH
    assert check("합성 설문에서 추천 응답이 49건이고 증가 폭은 12건이다.", ["survey:q09:1"]) == DROPPED_NUMBER_MISMATCH


def test_number_rules_rounding_and_labels():
    rows = [BY_ID["survey:q10:3"]]
    assert numbers_match("비율은 28.4%", rows, FAMILY, ROUND)
    assert numbers_match("비율은 28%", rows, FAMILY, ROUND)  # 비율 28.4를 소수 0자리로 반올림
    assert numbers_match("비율은 28.40%", rows, FAMILY, ROUND)
    assert not numbers_match("비율은 29%", rows, FAMILY, ROUND)
    assert not numbers_match("비율은 28.5%", rows, FAMILY, ROUND)
    assert numbers_match("2026-Q1 월 1~3회 응답이 28건", rows, FAMILY, ROUND)  # 라벨 속 숫자는 비교에서 뺀다
    assert not numbers_match("2026-Q1 월 1~3회 응답이 7건", rows, FAMILY, ROUND)
    assert numbers_match("q10 문항에서 28건", rows, FAMILY, ROUND)  # 문항 코드 속 숫자는 뺀다
    assert numbers_match("점수 3점", rows, FAMILY, ROUND)  # 선택지 번호 3
    assert numbers_match("1,234건", [{"item": "x", "metrics": {"건수": 1234}}], FAMILY, ROUND)


def test_a_sentence_must_use_values_of_the_rows_it_references():
    # 49는 survey:q09:1의 값이지만 survey:q01:5만 참조했으므로 일치하지 않는다
    assert check("합성 설문에서 만족 응답이 49건이다.", ["survey:q01:5"]) == DROPPED_NUMBER_MISMATCH
    assert check("합성 설문에서 만족 응답이 28건이다.", ["survey:q01:5"]) is None


def test_synthetic_word_is_required_for_survey_rows():
    assert check("추천한 적이 있다는 응답이 49건이다.", ["survey:q09:1"]) == DROPPED_OTHER
    assert check("VOC 전체 리뷰가 37건이다.", ["voc:total:count"]) is None  # 실측 행에는 필요 없다


def test_small_sample_word_is_required_for_small_sample_rows():
    assert check("판정 묶음 가중 평균 평점이 4.86이다.", ["voc:judged:mean_weighted"]) == DROPPED_OTHER
    assert check("표본이 적지만 판정 묶음 가중 평균 평점은 4.86이다.", ["voc:judged:mean_weighted"]) is None


def test_length_and_single_sentence_rules():
    long_sentence = "합성 " + "가" * 119
    assert len(long_sentence) == 122 and check(long_sentence, ["survey:q09:1"]) == DROPPED_OTHER
    assert check("합성 응답이다. 그리고 다른 문장이다.", ["survey:q09:1"]) == DROPPED_OTHER
    assert check("합성 설문에서 49건이고 비율은 49.0%이다.", ["survey:q09:1"]) is None  # 소수점은 문장 끝으로 세지 않는다
    assert check("   ", ["survey:q09:1"]) == DROPPED_OTHER
    at_limit = "합성" + "가" * 118
    assert len(at_limit) == 120 and check(at_limit, ["survey:q09:1"]) is None


def test_filter_counts_each_reason_and_keeps_order():
    items = [
        {"sentence": "합성 설문에서 추천 응답이 49건이다.", "row_ids": ["survey:q09:1"]},  # 통과
        {"sentence": "합성 설문에서 추천 응답이 50건이다.", "row_ids": ["survey:q09:1"]},  # 숫자 불일치
        {"sentence": "합성 설문 응답이 49건이다.", "row_ids": ["nope"]},  # 근거 없음
        {"sentence": "추천 응답이 49건이다.", "row_ids": ["survey:q09:1"]},  # 합성 누락
        {"sentence": "합성 설문에서 추천 응답이 49건이다.", "row_ids": ["survey:q09:1", "survey:q09:1"]},  # 중복 문장
        {"sentence": "VOC 전체 리뷰가 37건이다.", "row_ids": ["voc:total:count"]},  # 통과
    ]
    result = filter_suggestions(items, BY_ID, EVIDENCE, FAMILY, ROUND)
    assert result.counters == {
        "proposed": 6, "accepted": 2, "dropped_no_evidence": 1, "dropped_number_mismatch": 1, "dropped_other": 2,
    }
    assert [s["sentence"] for s in result.accepted] == ["합성 설문에서 추천 응답이 49건이다.", "VOC 전체 리뷰가 37건이다."]


def test_filter_keeps_at_most_five_sentences():
    items = [{"sentence": f"합성 설문 응답이 49건이다{'가' * n}", "row_ids": ["survey:q09:1"]} for n in range(7)]
    result = filter_suggestions(items, BY_ID, EVIDENCE, FAMILY, ROUND)
    assert result.counters["accepted"] == 5 and result.counters["dropped_other"] == 2 and result.counters["proposed"] == 7


# ---------- 비용 추정기 ----------
def test_cost_estimator_formula():
    prices = Prices(input_per_m=0.20, output_per_m=1.20)
    estimate = estimate_suggestion_cost(1000, 2000, prices)
    assert estimate.input_tokens == 2400  # (1000 + 2000) × 0.80
    # 출력 = 20 + 5 × (120 × 1.0 + 40) = 820
    assert estimate.output_tokens == 820
    assert estimate.one_pass_usd == pytest.approx(2400 * 0.20 / 1e6 + 820 * 1.20 / 1e6)
    assert estimate.upper_usd == pytest.approx(estimate.one_pass_usd * 3)
    assert SUGGESTION_CALIBRATION.retry_multiplier == 3


# ---------- 한글 수량 표현 (FR-0.3) ----------
KOREAN_QUANTITY_SENTENCES = [
    "합성 설문에서 추천 응답이 절반에 가깝다.",
    "합성 설문에서 추천 응답이 반절이다.",
    "합성 설문에서 추천 응답이 과반이다.",
    "합성 설문에서 추천 응답이 곱절로 늘었다.",
    "합성 설문에서 추천 응답이 몇 배 많다.",
    "합성 설문에서 추천 응답이 두 배다.",
    "합성 설문에서 추천 응답이 세 건 있다.",
    "합성 설문에서 추천 응답이 다섯 명이다.",
    "합성 설문에서 만족이 네 점이다.",
    "합성 설문에서 두 가지를 개선한다.",
    "합성 설문에서 열 개 문항이 있다.",
    "합성 설문에서 추천 응답이 삼 건이다.",
    "합성 설문에서 추천 응답이 이십 명이다.",
    "합성 설문에서 추천 응답이 오 점이다.",
    "합성 설문에서 추천 응답이 삼십 퍼센트다.",
    "합성 설문에서 추천 응답이 백 개다.",
]


@pytest.mark.parametrize("sentence", KOREAN_QUANTITY_SENTENCES)
def test_korean_quantity_expressions_are_dropped_as_number_mismatch(sentence):
    assert has_korean_quantity(sentence)
    assert check(sentence, ["survey:q09:1"]) == DROPPED_NUMBER_MISMATCH


def test_korean_quantity_check_runs_even_when_the_arabic_numbers_match():
    # 49건은 표와 같지만 한글 수량(절반)이 함께 있으면 제외한다
    assert check("합성 설문에서 추천 응답이 49건으로 절반에 가깝다.", ["survey:q09:1"]) == DROPPED_NUMBER_MISMATCH


@pytest.mark.parametrize(
    "sentence",
    [
        "합성 응답에서 q09 예 49건(49%)이라 추천 경로를 넓히는 안을 검토한다.",
        "합성 설문에서 만족한 건수가 49건이라 유지한다.",  # '만족한 건수'는 수량이 아니다
        "합성 설문에서 점수 개선이 필요하며 추천 응답은 49건이다.",  # 점수, 개선
        "합성 설문에서 대부분 추천하고 소수만 미추천이며 추천은 49건이다.",  # 질적 표현은 막지 않는다
        "합성 설문의 일부 응답을 보면 추천이 49건이다.",
    ],
)
def test_normal_and_qualitative_sentences_are_not_blocked(sentence):
    assert not has_korean_quantity(sentence)
    assert check(sentence, ["survey:q09:1"]) is None


def test_labels_are_removed_before_the_korean_quantity_check():
    rows = {"x": {"row_id": "x", "group": "설문", "source": "합성", "item": "개선할 점 — 한 가지 이상", "metrics": {"응답 수": 3}, "small_sample": False}}
    evidence = {"x": {"kind": "survey", "ids": [1]}}
    # 선택지 라벨에 든 '한 가지'는 라벨이므로 수량 표현으로 보지 않는다
    assert check_sentence({"sentence": "합성 설문의 한 가지 이상 응답은 3건이다.", "row_ids": ["x"]}, rows, evidence, FAMILY, ROUND) is None


EXPECTED_FINGERPRINT = "89d9ba3b327fa83f98a9f356e582b394dbd62d81bed11cf10d8a4a977adfb811"
