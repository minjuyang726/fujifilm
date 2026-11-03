"""호출 C 문항 형식·항목 결정, 영역 확인 문항 템플릿, 저장 형식 정규화(question-v4). 모든 값은 합성 설문 정의에서 온다."""

import pytest

from app.services import question_forms as forms
from app.services.synthetic_survey import QUESTIONS


def survey_options():
    """survey_question.options_json과 같은 모양: {문항 코드: [{code, label}]}."""
    return {code: [dict(option) for option in options] for code, _text, _kind, options in QUESTIONS}


def labels(items):
    return [item["label"] for item in items]


# ---------- 형식 결정 매핑 ----------
@pytest.mark.parametrize("question_code", ["q01", "q02", "q03", "q04", "q05"])
def test_scale5_source_questions_give_a_single_scale(question_code):
    spec = forms.decide_form([f"survey:{question_code}:4", f"survey:{question_code}:5"], survey_options())
    assert (spec.form, spec.source_question, spec.items) == ("scale10", question_code, [])


def test_r4_with_voc_rows_uses_the_q01_source():
    spec = forms.decide_form(["survey:q01:4", "survey:q01:5", "voc:judged:mean_unweighted", "voc:judged:count"], survey_options())
    assert (spec.form, spec.source_question) == ("scale10", "q01")


@pytest.mark.parametrize(
    "question_code, expected",
    [
        ("q06", ["여행", "모임·행사", "선물", "일상 기록"]),  # 5 기타 제외
        ("q07", ["필름·소모품 비용", "현상·인화 대기", "사용법", "결과물 품질"]),  # 5 불편한 점 없음 제외
        ("q08", ["필름·소모품 비용", "현상·인화 대기", "사용법 안내", "결과물 품질"]),  # 5 개선할 점 없음 제외
    ],
)
def test_category_source_questions_give_a_matrix_without_none_or_other(question_code, expected):
    spec = forms.decide_form([f"survey:{question_code}:2", f"survey:{question_code}:4"], survey_options())
    assert spec.form == "scale10_matrix" and spec.source_question == question_code
    assert labels(spec.items) == expected
    assert [item["code"] for item in spec.items] == ["1", "2", "3", "4"]
    excluded = {label for label in labels(survey_options()[question_code])} - set(expected)
    assert len(excluded) == 1 and excluded <= {"기타", "불편한 점 없음", "개선할 점 없음"}


def test_binary_and_ordinal_sources_give_a_single_scale():
    q09 = forms.decide_form(["survey:q09:2", "survey:q09:1"], survey_options())
    q10 = forms.decide_form(["survey:q10:2", "survey:q10:3"], survey_options())
    assert (q09.form, q09.source_question, q09.items) == ("scale10", "q09", [])
    assert (q10.form, q10.source_question, q10.items) == ("scale10", "q10", [])


def test_r3_uses_q09_as_the_source_in_either_row_order():
    spec = forms.decide_form(["survey:q01:4", "survey:q01:5", "survey:q09:2"], survey_options())
    assert (spec.form, spec.source_question, spec.items) == ("scale10", "q09", [])
    assert forms.decide_form(["survey:q09:2", "survey:q01:4", "survey:q01:5"], survey_options()).source_question == "q09"


def test_unknown_source_or_no_survey_row_gives_no_form():
    assert forms.decide_form(["voc:judged:count"], survey_options()) is None
    assert forms.decide_form(["survey:q99:1"], survey_options()) is None
    assert forms.decide_form([], survey_options()) is None
    assert forms.decide_form(["survey:respondents"], survey_options()) is None


def test_same_hypothesis_gives_the_same_form_and_items_regardless_of_other_inputs():
    options = survey_options()
    first = forms.decide_form(["survey:q06:2", "survey:q06:4"], options)
    second = forms.decide_form(["survey:q06:2", "survey:q06:4"], survey_options())  # 다른 제품군·회차에서 읽어도 정의가 같다
    assert first == second
    # 같은 문항의 다른 보기 쌍이어도 항목은 문항 정의에서 오므로 같다
    assert forms.decide_form(["survey:q06:1", "survey:q06:3"], options).items == first.items


def test_every_survey_question_has_a_form_and_matrix_questions_have_an_exclusion():
    assert set(forms.FORM_BY_SOURCE_QUESTION) == {code for code, *_ in QUESTIONS}
    for code, form in forms.FORM_BY_SOURCE_QUESTION.items():
        if form == forms.FORM_SCALE10_MATRIX:
            assert forms.EXCLUDED_ITEM_CODES[code]


# ---------- 영역 확인 문항 ----------
def test_opportunity_question_template_uses_the_four_q08_areas():
    question = forms.opportunity_question(survey_options())
    assert question["text"] == "다음 영역별로 개선이 필요한 정도를 눈금에서 골라 주세요."
    assert question["type"] == "scale10_matrix"
    assert question["options_json"] == {
        "kind": "opportunity_matrix", "low_label": "전혀 필요 없음", "high_label": "매우 필요함",
        "items": [{"code": "1", "label": "필름·소모품 비용"}, {"code": "2", "label": "현상·인화 대기"}, {"code": "3", "label": "사용법 안내"}, {"code": "4", "label": "결과물 품질"}],
    }


def test_opportunity_items_follow_the_survey_definition_not_a_hard_coded_list():
    options = survey_options()
    options["q08"][0]["label"] = "바뀐 이름"
    assert forms.opportunity_question(options)["options_json"]["items"][0] == {"code": "1", "label": "바뀐 이름"}


# ---------- 저장 형식 정규화: 두 options_json 형식을 같은 필드로 읽는다 ----------
def test_normalize_reads_the_question_v4_object_format():
    stored = forms.scale_options_json("hypothesis", "전혀 아님", "매우 그러함", [{"code": "1", "label": "여행"}])
    normalized = forms.normalize_question("scale10_matrix", stored)
    assert normalized == {
        "form": "scale10_matrix", "items": [{"code": "1", "label": "여행"}], "low_label": "전혀 아님", "high_label": "매우 그러함",
        "kind": "hypothesis", "options": [{"code": "1", "label": "여행"}],
    }
    single_bar = forms.normalize_question("scale10", forms.scale_options_json("hypothesis", "낮음", "높음", []))
    assert single_bar["items"] == [] and single_bar["options"] == [] and single_bar["low_label"] == "낮음"


def test_normalize_reads_the_question_v3_list_format():
    stored = [{"code": "1", "label": "여행"}, {"code": "2", "label": "모임"}]
    normalized = forms.normalize_question("single", stored)
    assert normalized == {"form": "single", "items": stored, "low_label": None, "high_label": None, "kind": "hypothesis", "options": stored}
    scale5 = forms.normalize_question("scale5", [{"code": str(i), "label": f"{i}점"} for i in range(1, 6)])
    assert scale5["form"] == "scale5" and len(scale5["items"]) == 5 and scale5["kind"] == "hypothesis"
    assert forms.normalize_question("scale5", None) == {"form": "scale5", "items": [], "low_label": None, "high_label": None, "kind": "hypothesis", "options": None}


def test_normalize_does_not_share_the_stored_objects():
    stored = forms.scale_options_json("hypothesis", "a", "b", [{"code": "1", "label": "x"}])
    normalized = forms.normalize_question("scale10_matrix", stored)
    normalized["items"][0]["label"] = "changed"
    assert stored["items"][0]["label"] == "x"


def test_is_card_sentence_tells_suggest_v4_cards_from_older_sentences():
    card = "합성 설문 기준 '결과물 품질' 영역 — 이 영역은 26.0%이며 2순위입니다. ▸ 산출물(FAQ 초안): 답변 초안입니다."
    assert forms.is_card_sentence(card)
    assert not forms.is_card_sentence("합성 설문에서 추천 응답이 49건이다.")
    assert not forms.is_card_sentence("쿠팡 리뷰 기준(실측) — 선택한 회차의 리뷰는 63건이다.")
