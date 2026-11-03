"""다음 회차 문항 초안의 형식·항목 결정과 저장 형식(question-v4, 결정 2026-11-03, 사용자 지시). LLM과 DB를 모른다.

코드가 형식과 항목을 정하고 모델은 문구(text, low_label, high_label)만 쓴다.
- 가설의 출처 문항을 related_row_ids(survey:{문항}:{보기})에서 찾고, 출처 문항에 따라 형식을 정한다(FORM_BY_SOURCE_QUESTION).
- scale10: 0~10 눈금 막대 하나. scale10_matrix: 같은 눈금을 항목마다 하나씩(항목은 출처 문항 보기에서 "없음"·"기타"류를 뺀 것을 코드가 그대로 넣는다).
- 같은 가설이면 제품군·회차와 관계없이 같은 형식과 같은 항목이 나온다(합성 설문의 문항 정의가 회차마다 같기 때문이다).
- 액션 카드가 있는 리포트에는 영역 확인 문항(opportunity_matrix, 코드 템플릿)을 맨 앞에 항상 넣는다.
저장은 기존 next_survey_question 컬럼 그대로다. type = 형식, options_json = 객체 {kind, low_label, high_label, items}.
question-v3까지의 행(scale5/single/multi, options_json은 목록)도 normalize_question이 같은 필드로 읽는다.
"""

from dataclasses import dataclass, field

from app.services.action_cards import AREA_QUESTION_CODE, CARD_SEPARATOR, DELIVERABLE_LABEL, EXCLUDED_OPTION_CODES

FORM_SCALE10 = "scale10"
FORM_SCALE10_MATRIX = "scale10_matrix"
LEGACY_FORMS = ("scale5", "single", "multi")
NEW_FORMS = (FORM_SCALE10, FORM_SCALE10_MATRIX)

KIND_HYPOTHESIS = "hypothesis"
KIND_OPPORTUNITY = "opportunity_matrix"

# 가설의 출처 문항 -> 초안 형식. 합성 설문 정의(app/services/synthetic_survey.py QUESTIONS)에서
# q01~q05는 5점 척도(만족·결과물·사용성·가치·재구매 의향) -> 눈금 하나,
# q06(사용 상황)·q07(불편한 점)·q08(개선 영역)은 범주 보기 -> 항목마다 눈금(매트릭스),
# q09는 이분형 추천 경험 -> 추천 의향 눈금 하나, q10은 순서형 사용 빈도 -> 사용 빈도 눈금 하나.
FORM_BY_SOURCE_QUESTION = {
    "q01": FORM_SCALE10, "q02": FORM_SCALE10, "q03": FORM_SCALE10, "q04": FORM_SCALE10, "q05": FORM_SCALE10,
    "q06": FORM_SCALE10_MATRIX, "q07": FORM_SCALE10_MATRIX, "q08": FORM_SCALE10_MATRIX,
    "q09": FORM_SCALE10, "q10": FORM_SCALE10,
}
# 매트릭스 항목에서 뺄 보기(없음·기타류). 코드는 선택지 번호다: q06 5=기타, q07 5=불편한 점 없음, q08 5=개선할 점 없음.
EXCLUDED_ITEM_CODES = {"q06": ("5",), "q07": ("5",), "q08": EXCLUDED_OPTION_CODES}

# R3(q01 만족 x q09 추천 안 함의 불일치)는 q09 쪽을 출처로 삼아 눈금 하나로 묻는다.
# 이유: 만족(q01)은 이미 다음 회차에도 같은 문항으로 물을 핵심 문항이고, 어긋남을 가려내는 데 필요한 것은 행동 의향인 추천 쪽의 정도다.
R3_QUESTIONS = {"q01", "q09"}
R3_SOURCE_QUESTION = "q09"

OPPORTUNITY_TEXT = "다음 영역별로 개선이 필요한 정도를 눈금에서 골라 주세요."
OPPORTUNITY_LOW_LABEL = "전혀 필요 없음"
OPPORTUNITY_HIGH_LABEL = "매우 필요함"
OPPORTUNITY_STATEMENT = "액션 카드의 개선 영역 우선순위를 다음 회차에서 확인하는 문항이다."
OPPORTUNITY_HYPOTHESIS_KIND = "opportunity"  # 가설이 없어서 화면의 가설 종류 칸에 쓰는 표시 값이다


@dataclass(frozen=True)
class FormSpec:
    form: str
    source_question: str
    items: list[dict] = field(default_factory=list)  # [{"code", "label"}], scale10은 빈 목록


def source_questions(related_row_ids: list[str]) -> list[str]:
    """related_row_ids에서 설문 문항 코드를 나온 순서대로 중복 없이 뽑는다(survey:respondents와 VOC 행은 뺀다)."""
    codes: list[str] = []
    for row_id in related_row_ids:
        parts = row_id.split(":")
        if len(parts) == 3 and parts[0] == "survey" and parts[1] != "respondents" and parts[1] not in codes:
            codes.append(parts[1])
    return codes


def items_for(question_code: str, options: list[dict]) -> list[dict]:
    excluded = EXCLUDED_ITEM_CODES.get(question_code, ())
    return [{"code": option["code"], "label": option["label"]} for option in options if option["code"] not in excluded]


def decide_form(related_row_ids: list[str], survey_options: dict[str, list[dict]]) -> FormSpec | None:
    """가설 하나의 문항 형식과 항목. 출처 설문 문항을 못 찾거나 알 수 없는 문항이면 None이다.

    survey_options: {문항 코드: [{"code", "label"}, ...]} (survey_question.options_json)."""
    codes = source_questions(related_row_ids)
    if not codes:
        return None
    source = R3_SOURCE_QUESTION if set(codes) == R3_QUESTIONS else codes[0]
    form = FORM_BY_SOURCE_QUESTION.get(source)
    if form is None:
        return None
    items = items_for(source, survey_options.get(source, [])) if form == FORM_SCALE10_MATRIX else []
    return FormSpec(form=form, source_question=source, items=items)


def opportunity_question(survey_options: dict[str, list[dict]]) -> dict:
    """영역 확인 문항(코드 템플릿). 항목은 q08의 영역 보기("개선할 점 없음" 제외)다."""
    return {
        "text": OPPORTUNITY_TEXT,
        "type": FORM_SCALE10_MATRIX,
        "options_json": scale_options_json(
            KIND_OPPORTUNITY, OPPORTUNITY_LOW_LABEL, OPPORTUNITY_HIGH_LABEL, items_for(AREA_QUESTION_CODE, survey_options.get(AREA_QUESTION_CODE, []))
        ),
    }


def scale_options_json(kind: str, low_label: str, high_label: str, items: list[dict]) -> dict:
    """scale10/scale10_matrix의 options_json."""
    return {"kind": kind, "low_label": low_label, "high_label": high_label, "items": [dict(item) for item in items]}


def is_card_sentence(sentence: str) -> bool:
    """suggest-v4 액션 카드의 저장 문장인지(우선순위 문장 ▸ 산출물(...): 본문). suggest-v3 문장은 아니다."""
    return f"{CARD_SEPARATOR}{DELIVERABLE_LABEL}(" in sentence


def normalize_question(question_type: str, options_json) -> dict:
    """저장된 type과 options_json을 두 형식에서 같은 필드로 읽는다: form, items, low_label, high_label, kind, options.

    - question-v4(scale10, scale10_matrix): options_json이 객체. options는 items와 같은 목록이다(기존 화면이 목록으로 읽을 수 있게).
    - question-v3 이전(scale5, single, multi): options_json이 [{code, label}] 목록이거나 None. 양끝 라벨은 없고 kind는 hypothesis다."""
    if isinstance(options_json, dict):
        items = [dict(item) for item in options_json.get("items") or []]
        return {
            "form": question_type, "items": items, "low_label": options_json.get("low_label"), "high_label": options_json.get("high_label"),
            "kind": options_json.get("kind") or KIND_HYPOTHESIS, "options": items,
        }
    items = [dict(item) for item in options_json or []]
    return {"form": question_type, "items": items, "low_label": None, "high_label": None, "kind": KIND_HYPOTHESIS, "options": options_json}
