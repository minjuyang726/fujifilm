"""액션 카드의 코드 쪽 계산(suggest-v4, 결정 2026-11-03, 사용자 지시). LLM과 DB를 모른다.

- 개선 영역: 설문 q08(개선되었으면 하는 점, 복수 선택)의 보기에서 EXCLUDED_OPTION_CODES("개선할 점 없음")를 뺀 보기들.
  라벨은 survey_question.options_json에서 읽어 넘겨받는다.
- 순위: q08 선택 응답자 수 내림차순, 동률은 보기 코드 순. 상위 TOP_AREAS개만 카드로 만든다.
- 순위 신뢰도: 인접 순위(1·2위, 2·3위)의 선택 비율 차이가 우연 범위인지 짝지은 비율 검정으로 계산한다.
  같은 응답자가 두 영역을 함께 고를 수 있어서 응답자별 선택(스냅샷의 허용 목록)으로 b = A만 선택, c = B만 선택, n = 응답자 수를 센다.
  d = (b - c) / n, Var = ((b + c) / n - d^2) / n 이고 |d| <= 1.96 x sqrt(Var) 이면 차이가 우연 범위(tie)다.
- 순위 라벨은 코드가 만든다: 1순위 / 공동 1순위(1위와 2위가 tie), 2순위 / 공동 2순위(2위와 3위가 tie), 3순위.
- 쿠팡 리뷰 카드는 코드 템플릿이다(모델 호출 없음).
임계값(1.96, 상위 3개)은 근거 없는 임시 가정이다.
"""

import math
from dataclasses import dataclass, field

AREA_QUESTION_CODE = "q08"
# q08의 마지막 보기(5)는 "개선할 점 없음"으로, 다른 보기와 함께 고를 수 없는 배타 보기다(app/services/synthetic_survey.py EXCLUSIVE).
# 개선 영역이 아니므로 영역 목록에서 뺀다.
EXCLUDED_OPTION_CODES = ("5",)
TOP_AREAS = 3
TIE_Z = 1.96
# q07(가장 불편했던 점)과 q08의 보기 1~4는 같은 주제의 같은 순서로 정의되어 있다(합성 설문 정의). 같은 코드의 q07 행이 있으면 근거에 더한다.
RELATED_QUESTION_CODE = "q07"

SYNTHETIC_PREFIX = "합성 설문 기준"
REVIEW_PREFIX = "쿠팡 리뷰 기준(실측)"
DELIVERABLE_LABEL = "산출물"
CARD_SEPARATOR = " ▸ "
REVIEW_ROW_IDS = ["voc:total:count", "voc:no_text:count", "voc:judged:count"]


@dataclass
class Area:
    code: str
    label: str
    count: int  # q08에서 이 보기를 고른 응답자 수
    pct: float  # 표의 비율(%) 값 그대로
    rank: int  # 1부터
    rank_label: str = ""
    joint: bool = False
    row_ids: list[str] = field(default_factory=list)


def paired_tie(ids_a: set[int], ids_b: set[int], n: int) -> bool:
    """두 영역의 선택 비율 차이가 우연 범위이면 참(경계 포함). 같은 응답자의 복수 선택을 짝지어 비교한다."""
    if n <= 0:
        return False
    b = len(ids_a - ids_b)
    c = len(ids_b - ids_a)
    d = (b - c) / n
    variance = max(((b + c) / n - d * d) / n, 0.0)
    return abs(d) <= TIE_Z * math.sqrt(variance)


def rank_labels(tie_first_second: bool, tie_second_third: bool, areas_count: int) -> list[tuple[str, bool]]:
    """(순위 라벨, 공동 여부)를 1위부터 돌려준다."""
    labels = [("공동 1순위", True) if tie_first_second else ("1순위", False)]
    if areas_count >= 2:
        labels.append(("공동 2순위", True) if tie_second_third else ("2순위", False))
    if areas_count >= 3:
        labels.append(("3순위", False))
    return labels[:areas_count]


def select_areas(table: dict, allowed_evidence: dict, option_labels: dict[str, str]) -> list[Area]:
    """영역을 순위 순서로 돌려준다(최대 TOP_AREAS개). 후보가 없으면 빈 목록이다."""
    rows_by_id = {row["row_id"]: row for row in table["rows"]}
    respondents = rows_by_id.get("survey:respondents", {}).get("metrics", {}).get("응답자 수", 0)
    candidates = []
    for code, label in option_labels.items():
        if code in EXCLUDED_OPTION_CODES:
            continue
        row = rows_by_id.get(f"survey:{AREA_QUESTION_CODE}:{code}")
        if row is None:
            continue
        candidates.append((-row["metrics"]["응답 수"], code, label, row))
    candidates.sort(key=lambda item: (item[0], item[1]))
    top = candidates[:TOP_AREAS]
    ids = [set(allowed_evidence.get(f"survey:{AREA_QUESTION_CODE}:{code}", {}).get("ids", [])) for _, code, _, _ in top]
    tie_first_second = len(top) >= 2 and paired_tie(ids[0], ids[1], respondents)
    tie_second_third = len(top) >= 3 and paired_tie(ids[1], ids[2], respondents)
    labels = rank_labels(tie_first_second, tie_second_third, len(top))
    areas = []
    for index, (negative_count, code, label, row) in enumerate(top):
        row_ids = [f"survey:{AREA_QUESTION_CODE}:{code}"]
        related = f"survey:{RELATED_QUESTION_CODE}:{code}"
        if related in rows_by_id:
            row_ids.append(related)
        areas.append(
            Area(
                code=code, label=label, count=-negative_count, pct=row["metrics"]["비율(%)"], rank=index + 1,
                rank_label=labels[index][0], joint=labels[index][1], row_ids=row_ids,
            )
        )
    return areas


def fill_placeholders(sentence: str, area: Area) -> str:
    """{pct}는 그 영역의 q08 선택 비율(표의 값 그대로, % 붙임), {rank}는 순위 라벨로 바꾼다."""
    return sentence.replace("{pct}", f"{area.pct}%").replace("{rank}", area.rank_label)


def render_area_card(area: Area, priority_sentence: str, deliverable_kind: str, deliverable_text: str) -> str:
    """저장할 문장. '합성 설문 기준'은 코드가 붙인다(모델이 쓰지 않는다). 카드 구조는 구분자로 나눈다:
    합성 설문 기준 '라벨' 영역 — 우선순위 문장 ▸ 산출물(종류): 본문"""
    head = f"{SYNTHETIC_PREFIX} '{area.label}' 영역 — {fill_placeholders(priority_sentence.strip(), area)}"
    return f"{head}{CARD_SEPARATOR}{DELIVERABLE_LABEL}({deliverable_kind}): {deliverable_text.strip()}"


def review_card(rows_by_id: dict) -> tuple[str, list[str]] | None:
    """쿠팡 리뷰 카드(코드 템플릿). 필요한 행이 없으면 None. (문장, row_ids)를 돌려준다."""
    total = rows_by_id.get("voc:total:count")
    no_text = rows_by_id.get("voc:no_text:count")
    judged = rows_by_id.get("voc:judged:count")
    if total is None or no_text is None or judged is None:
        return None
    sentence = (
        f"{REVIEW_PREFIX} — 선택한 회차의 리뷰는 {total['metrics']['리뷰 수']}건이고, "
        f"그중 제목·본문 없음이 {no_text['metrics']['건수']}건, 판정이 끝난 글이 {judged['metrics']['건수']}건이다."
    )
    if judged.get("small_sample"):
        sentence += " 판정 표본이 적어 영역 우선순위는 설문 기준으로만 정했다."
    return sentence, list(REVIEW_ROW_IDS)
