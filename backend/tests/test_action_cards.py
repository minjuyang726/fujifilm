"""액션 카드의 코드 쪽 계산(영역 선정, 순위, 짝지은 비율 검정, 순위 라벨, 자리표시자 치환, 쿠팡 리뷰 카드). 모든 값은 가짜다."""

import pytest

from app.services import action_cards as cards

LABELS = {"1": "필름·소모품 비용", "2": "현상·인화 대기", "3": "사용법 안내", "4": "결과물 품질", "5": "개선할 점 없음"}


def make_table(counts: dict, n=100, with_q07=True, judged=4, small=True):
    """counts: {보기 코드: 응답자 수}. q08 행을 만든다. 근거는 응답자 번호 1..count를 순서대로 쓴 허용 목록이다."""
    rows = [{"row_id": "survey:respondents", "group": "설문", "source": "합성", "item": "설문 응답자 수", "metrics": {"응답자 수": n}, "small_sample": False}]
    evidence = {}
    for code, count in counts.items():
        rows.append({"row_id": f"survey:q08:{code}", "group": "설문", "source": "합성", "item": f"개선되었으면 하는 점은? — {LABELS[code]}",
                     "metrics": {"응답 수": count, "비율(%)": round(count / n * 100, 1), "선택지 번호": int(code)}, "small_sample": False})
        evidence[f"survey:q08:{code}"] = {"kind": "survey", "ids": list(range(1, count + 1))}
        if with_q07 and code != "5":
            rows.append({"row_id": f"survey:q07:{code}", "group": "설문", "source": "합성", "item": f"불편했던 점은? — {LABELS[code]}",
                         "metrics": {"응답 수": 10, "비율(%)": 10.0, "선택지 번호": int(code)}, "small_sample": False})
    rows += [
        {"row_id": "voc:total:count", "group": "VOC", "source": "실측", "item": "VOC 전체 리뷰", "metrics": {"리뷰 수": 63}, "small_sample": False},
        {"row_id": "voc:no_text:count", "group": "VOC", "source": "실측", "item": "제목·본문 없음 묶음", "metrics": {"건수": 50}, "small_sample": False},
        {"row_id": "voc:judged:count", "group": "VOC", "source": "실측", "item": "판정 묶음", "metrics": {"건수": judged, "표본 적음 기준(건)": 30}, "small_sample": small},
    ]
    return {"family": "가", "round": "2026-Q1", "rows": rows}, evidence


# ---------- 짝지은 비율 검정 ----------
def sets(b: int, c: int, shared: int = 20):
    """b = A만 선택, c = B만 선택, shared = 둘 다 선택한 응답자 수."""
    common = set(range(1, shared + 1))
    a_only = set(range(1000, 1000 + b))
    b_only = set(range(2000, 2000 + c))
    return common | a_only, common | b_only


def test_paired_tie_boundary_values_n100():
    # b=13, c=5: d=0.08 <= 1.96 x sqrt(((18/100) - 0.0064) / 100) = 0.0817 -> 우연 범위
    assert cards.paired_tie(*sets(13, 5), 100) is True
    # b=14, c=5: d=0.09 > 0.0836 -> 우연 범위가 아니다
    assert cards.paired_tie(*sets(14, 5), 100) is False
    # 부호가 바뀌어도 같다
    assert cards.paired_tie(*sets(5, 14), 100) is False and cards.paired_tie(*sets(5, 13), 100) is True


def test_paired_tie_equal_selections_is_a_tie_and_the_boundary_is_inclusive():
    same = set(range(1, 31))
    assert cards.paired_tie(same, set(same), 100) is True  # b = c = 0: |d| = 0 <= 0 (경계 포함)
    assert cards.paired_tie(*sets(7, 7), 100) is True  # b = c: d = 0


def test_paired_tie_guards_zero_respondents():
    assert cards.paired_tie({1}, {1}, 0) is False


def test_paired_tie_matches_the_formula():
    a, b = sets(13, 5)
    n = 100
    d = (13 - 5) / n
    variance = ((13 + 5) / n - d * d) / n
    assert cards.paired_tie(a, b, n) == (abs(d) <= 1.96 * variance ** 0.5)


# ---------- 순위 라벨 ----------
@pytest.mark.parametrize(
    "tie12, tie23, expected",
    [
        (False, False, [("1순위", False), ("2순위", False), ("3순위", False)]),
        (True, False, [("공동 1순위", True), ("2순위", False), ("3순위", False)]),
        (False, True, [("1순위", False), ("공동 2순위", True), ("3순위", False)]),
        (True, True, [("공동 1순위", True), ("공동 2순위", True), ("3순위", False)]),
    ],
)
def test_rank_labels(tie12, tie23, expected):
    assert cards.rank_labels(tie12, tie23, 3) == expected


def test_rank_labels_with_fewer_areas():
    assert cards.rank_labels(True, True, 2) == [("공동 1순위", True), ("공동 2순위", True)]
    assert cards.rank_labels(False, False, 1) == [("1순위", False)]


# ---------- 영역 선정 ----------
def test_top_three_by_selection_count_excluding_the_none_option():
    table, evidence = make_table({"1": 20, "2": 70, "3": 30, "4": 50, "5": 90})
    areas = cards.select_areas(table, evidence, LABELS)
    assert [a.code for a in areas] == ["2", "4", "3"]  # 보기 5(개선할 점 없음)는 90명이어도 영역이 아니다
    assert [a.rank for a in areas] == [1, 2, 3]
    assert areas[0].label == "현상·인화 대기" and areas[0].count == 70 and areas[0].pct == 70.0
    assert [a.rank_label for a in areas] == ["1순위", "2순위", "3순위"]


def test_ties_in_count_are_ordered_by_option_code():
    table, evidence = make_table({"1": 40, "2": 40, "3": 40, "4": 40})
    assert [a.code for a in cards.select_areas(table, evidence, LABELS)] == ["1", "2", "3"]


def test_row_ids_include_the_same_area_in_q07_when_present():
    table, evidence = make_table({"1": 60, "2": 40, "3": 20, "4": 10})
    areas = cards.select_areas(table, evidence, LABELS)
    assert areas[0].row_ids == ["survey:q08:1", "survey:q07:1"]
    table, evidence = make_table({"1": 60, "2": 40, "3": 20, "4": 10}, with_q07=False)
    assert cards.select_areas(table, evidence, LABELS)[0].row_ids == ["survey:q08:1"]


def test_joint_labels_come_from_the_paired_test_on_respondent_level_selections():
    # 1위(60명)와 2위(57명)는 응답자 3명 차이라 우연 범위(b=3, c=0, n=100: |d|=0.03 <= 0.0334), 3위(20명)는 확실히 낮다
    table, evidence = make_table({"1": 60, "2": 57, "3": 20})
    areas = cards.select_areas(table, evidence, LABELS)
    assert [(a.rank_label, a.joint) for a in areas] == [("공동 1순위", True), ("2순위", False), ("3순위", False)]


def test_a_clear_gap_gives_separate_ranks():
    # 60명과 55명: b=5, c=0이면 |d|=0.05 > 0.0427 이라 우연 범위가 아니다
    table, evidence = make_table({"1": 60, "2": 55, "3": 20})
    assert [a.rank_label for a in cards.select_areas(table, evidence, LABELS)] == ["1순위", "2순위", "3순위"]


def test_fewer_candidates_and_no_candidates():
    table, evidence = make_table({"1": 30})
    areas = cards.select_areas(table, evidence, {"1": "필름·소모품 비용", "5": "개선할 점 없음"})
    assert len(areas) == 1 and areas[0].rank_label in ("1순위", "공동 1순위")
    assert cards.select_areas(table, evidence, {"5": "개선할 점 없음"}) == []


def test_labels_come_from_the_given_option_labels():
    table, evidence = make_table({"1": 60, "2": 40, "3": 20, "4": 10})
    areas = cards.select_areas(table, evidence, {**LABELS, "1": "바뀐 이름"})
    assert areas[0].label == "바뀐 이름"


# ---------- 자리표시자와 렌더링 ----------
def sample_area(joint=False, label="결과물 품질", pct=26.0):
    return cards.Area(code="4", label=label, count=26, pct=pct, rank=2, rank_label="공동 2순위" if joint else "2순위", joint=joint,
                      row_ids=["survey:q08:4", "survey:q07:4"])


def test_placeholders_are_filled_with_the_table_value_and_the_rank_label():
    area = sample_area()
    assert cards.fill_placeholders("이 영역은 {pct}이며 {rank}입니다.", area) == "이 영역은 26.0%이며 2순위입니다."
    assert cards.fill_placeholders("이 영역은 {pct}이며 {rank}입니다.", sample_area(joint=True)) == "이 영역은 26.0%이며 공동 2순위입니다."


def test_card_sentence_format_has_the_synthetic_prefix_label_and_deliverable():
    text = cards.render_area_card(sample_area(), "이 영역은 {pct}이며 {rank}입니다.", "FAQ 초안", "문의 답변 초안입니다. 기간은 [확인 필요]입니다.")
    assert text == "합성 설문 기준 '결과물 품질' 영역 — 이 영역은 26.0%이며 2순위입니다. ▸ 산출물(FAQ 초안): 문의 답변 초안입니다. 기간은 [확인 필요]입니다."
    head, deliverable = text.split(cards.CARD_SEPARATOR)
    assert head.startswith(cards.SYNTHETIC_PREFIX) and deliverable.startswith("산출물(FAQ 초안): ")


# ---------- 쿠팡 리뷰 카드 ----------
def test_review_card_template_with_small_judged_sample():
    table, _ = make_table({"1": 10}, judged=4, small=True)
    rows = {r["row_id"]: r for r in table["rows"]}
    sentence, row_ids = cards.review_card(rows)
    assert sentence == (
        "쿠팡 리뷰 기준(실측) — 선택한 회차의 리뷰는 63건이고, 그중 제목·본문 없음이 50건, 판정이 끝난 글이 4건이다. "
        "판정 표본이 적어 영역 우선순위는 설문 기준으로만 정했다."
    )
    assert row_ids == ["voc:total:count", "voc:no_text:count", "voc:judged:count"]


def test_review_card_without_the_small_sample_note():
    table, _ = make_table({"1": 10}, judged=40, small=False)
    sentence, _ = cards.review_card({r["row_id"]: r for r in table["rows"]})
    assert "표본" not in sentence and "판정이 끝난 글이 40건" in sentence


def test_review_card_is_none_when_rows_are_missing():
    assert cards.review_card({}) is None
