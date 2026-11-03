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


# ---------- 순위 그룹과 라벨 (그룹 대표 기준 비교) ----------
def labels_for(counts: dict):
    """코드 1~3의 선택 응답자 수로 만든 영역의 순위 라벨. 근거는 1..count의 포함 관계(앞 영역이 뒤 영역을 포함)다."""
    table, evidence = make_table(counts)
    return [(a.code, a.rank_label, a.joint) for a in cards.select_areas(table, evidence, LABELS)]


def test_all_three_areas_indistinguishable_from_the_leader_are_joint_first():
    # 60 vs 57: b=3 -> |d|=0.03 <= 0.0334, 60 vs 58도 같은 그룹
    assert labels_for({"1": 60, "2": 58, "3": 57}) == [("1", "공동 1순위", True), ("2", "공동 1순위", True), ("3", "공동 1순위", True)]


def test_second_joins_the_leader_and_third_is_distinct():
    # 60 vs 50: b=10 -> |d|=0.10 > 0.0588 이라 구분된다
    assert labels_for({"1": 60, "2": 57, "3": 50}) == [("1", "공동 1순위", True), ("2", "공동 1순위", True), ("3", "3순위", False)]


def test_only_the_leader_is_distinct_and_second_and_third_are_grouped():
    # 45 vs 60: 구분됨 -> 2위가 새 그룹의 대표. 42 vs 45: b=3 -> 같은 그룹
    assert labels_for({"1": 60, "2": 45, "3": 42}) == [("1", "1순위", False), ("2", "공동 2순위", True), ("3", "공동 2순위", True)]


def test_all_three_distinct():
    # 60 vs 45(b=15), 45 vs 30(b=15)
    assert labels_for({"1": 60, "2": 45, "3": 30}) == [("1", "1순위", False), ("2", "2순위", False), ("3", "3순위", False)]


def test_comparison_is_with_the_group_leader_not_with_the_adjacent_area():
    # 57 vs 60(b=3) 같은 그룹. 54 vs 인접 57은 b=3이라 구분되지 않지만, 대표 60과는 b=6(|d|=0.06 > 0.0466)이라 구분된다 -> 3순위
    assert labels_for({"1": 60, "2": 57, "3": 54}) == [("1", "공동 1순위", True), ("2", "공동 1순위", True), ("3", "3순위", False)]


def test_boundary_values_decide_the_group():
    # 경계: b=13,c=5(n=100)는 우연 범위, b=14,c=5는 아니다. 선두와 둘째의 차이만 바꿔 라벨이 바뀌는 지점을 확인한다.
    assert cards.paired_tie(*sets(13, 5), 100) is True and cards.paired_tie(*sets(14, 5), 100) is False
    assert cards.rank_groups([*sets(13, 5)], 100) == [(1, 2, True), (1, 2, True)]
    assert cards.rank_groups([*sets(14, 5)], 100) == [(1, 1, False), (2, 1, False)]


def test_rank_k_is_the_leader_position_and_label_format():
    assert cards.rank_label(1, False) == "1순위" and cards.rank_label(1, True) == "공동 1순위"
    assert cards.rank_label(2, True) == "공동 2순위" and cards.rank_label(3, False) == "3순위"
    assert cards.rank_groups([{1, 2, 3}], 10) == [(1, 1, False)]  # 영역이 하나뿐이면 단독 1순위


def test_paired_stats_reports_the_numbers_used():
    stats = cards.paired_stats(*sets(13, 5), 100)
    assert (stats.b, stats.c, stats.n) == (13, 5, 100)
    assert stats.difference == pytest.approx(0.08)
    assert stats.critical == pytest.approx(1.96 * (((13 + 5) / 100 - 0.08 ** 2) / 100) ** 0.5)
    assert stats.tie is True


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
    # 1위(60명)와 2위(57명)는 응답자 3명 차이라 우연 범위(b=3, c=0, n=100: |d|=0.03 <= 0.0334), 3위(20명)는 선두와 구분된다
    table, evidence = make_table({"1": 60, "2": 57, "3": 20})
    areas = cards.select_areas(table, evidence, LABELS)
    assert [(a.rank_label, a.joint) for a in areas] == [("공동 1순위", True), ("공동 1순위", True), ("3순위", False)]


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
        "쿠팡 리뷰 기준(실측) — 선택한 회차의 리뷰는 63건이고, 그중 제목·본문 없음이 50건, 판정이 끝난 글이 4건입니다. "
        "판정 표본이 적어 영역 우선순위는 설문 기준으로만 정했습니다."
    )
    assert row_ids == ["voc:total:count", "voc:no_text:count", "voc:judged:count"]


def test_review_card_without_the_small_sample_note():
    table, _ = make_table({"1": 10}, judged=40, small=False)
    sentence, _ = cards.review_card({r["row_id"]: r for r in table["rows"]})
    assert "표본" not in sentence and "판정이 끝난 글이 40건" in sentence


def test_review_card_is_none_when_rows_are_missing():
    assert cards.review_card({}) is None


# ---------- q07과 q08의 같은 영역 매핑 ----------


def test_q08_to_q07_mapping_points_at_the_same_area_in_the_survey_definition():
    from app.services.synthetic_survey import QUESTIONS

    options = {code: {o["code"]: o["label"] for o in opts} for code, _text, _kind, opts in QUESTIONS}
    assert set(cards.Q08_TO_Q07_OPTION) == {"1", "2", "3", "4"}  # 개선할 점 없음(5)은 영역이 아니라 매핑에 없다
    for q08_code, q07_code in cards.Q08_TO_Q07_OPTION.items():
        q08_label, q07_label = options["q08"][q08_code], options["q07"][q07_code]
        assert q08_label == q07_label, (q08_code, q08_label, q07_label)  # 예외 없이 같은 라벨이다(q07의 "사용법"을 "사용법 안내"로 통일했다)


def test_old_db_label_is_unified_by_the_canonical_label_helper():
    assert cards.canonical_label("사용법") == "사용법 안내" and cards.canonical_label("사용법 안내") == "사용법 안내"
    assert cards.canonical_label("결과물 품질") == "결과물 품질"
    # 이미 적재된 DB의 q07·q08 라벨 쌍은 통일한 뒤 같아진다
    for q08_label, q07_label in (("필름·소모품 비용", "필름·소모품 비용"), ("사용법 안내", "사용법")):
        assert cards.canonical_label(q08_label) == cards.canonical_label(q07_label)


def test_select_areas_uses_the_mapping_constant(monkeypatch):
    table, evidence = make_table({"1": 60, "2": 40, "3": 20, "4": 10})
    monkeypatch.setattr(cards, "Q08_TO_Q07_OPTION", {"1": "2", "2": "1", "3": "3", "4": "4"})
    areas = cards.select_areas(table, evidence, LABELS)
    assert areas[0].row_ids == ["survey:q08:1", "survey:q07:2"]
    assert areas[1].row_ids == ["survey:q08:2", "survey:q07:1"]


def test_an_option_without_a_mapping_gets_no_q07_row(monkeypatch):
    table, evidence = make_table({"1": 60, "2": 40, "3": 20, "4": 10})
    monkeypatch.setattr(cards, "Q08_TO_Q07_OPTION", {"2": "2"})
    areas = cards.select_areas(table, evidence, LABELS)
    assert areas[0].row_ids == ["survey:q08:1"] and areas[1].row_ids == ["survey:q08:2", "survey:q07:2"]


# ---------- 저장된 카드 문장 쪼개기 ----------
def test_parse_an_area_card_sentence():
    sentence = cards.render_area_card(sample_area(joint=True), "이 영역은 {pct}이며 {rank}입니다.", "FAQ 초안", "문의 답변 초안입니다. 기간은 [확인 필요]입니다.")
    assert cards.parse_card_sentence(sentence) == {
        "card_kind": "area", "area_label": "결과물 품질", "rank_label": "공동 2순위", "priority_text": "이 영역은 26.0%이며 공동 2순위입니다.",
        "deliverable_kind": "FAQ 초안", "deliverable_text": "문의 답변 초안입니다. 기간은 [확인 필요]입니다.",
    }


def test_parse_keeps_label_text_with_punctuation_and_a_plain_rank():
    parsed = cards.parse_card_sentence(cards.render_area_card(sample_area(label="필름·소모품 비용"), "이 영역은 {pct}이며 {rank}입니다.", "내부 보고 문단", "보고 문단입니다."))
    assert (parsed["area_label"], parsed["rank_label"], parsed["deliverable_kind"]) == ("필름·소모품 비용", "2순위", "내부 보고 문단")


def test_parse_the_review_card_and_legacy_sentences():
    table, _ = make_table({"1": 10}, judged=4, small=True)
    review_sentence, _row_ids = cards.review_card({r["row_id"]: r for r in table["rows"]})
    voc = cards.parse_card_sentence(review_sentence)
    assert voc["card_kind"] == "voc" and voc["priority_text"] == review_sentence and voc["area_label"] is None and voc["deliverable_text"] is None
    legacy = cards.parse_card_sentence("합성 설문에서 지인에게 추천한 적이 있다는 응답이 49건이라 추천 경로를 넓히는 안을 검토한다.")
    assert legacy["card_kind"] == "legacy" and legacy["priority_text"].startswith("합성 설문에서") and legacy["rank_label"] is None


@pytest.mark.parametrize("broken", [
    "합성 설문 기준 '라벨' 영역 — 산출물 구분자가 없다",
    "합성 설문 기준 영역 — 라벨 따옴표가 없다 ▸ 산출물(FAQ 초안): 본문",
    "합성 설문 기준 '라벨' 영역 — 문장 ▸ 산출물 FAQ 초안: 괄호가 없다",
    "", "   ",
])
def test_parse_treats_broken_formats_as_legacy_without_raising(broken):
    parsed = cards.parse_card_sentence(broken)
    assert parsed["card_kind"] == "legacy" and parsed["priority_text"] == broken


def test_parse_does_not_raise_for_non_strings():
    assert cards.parse_card_sentence(None)["card_kind"] == "legacy"
    assert cards.parse_card_sentence(123)["priority_text"] == "123"


def test_parse_area_card_without_a_rank_in_the_text_has_no_rank_label():
    parsed = cards.parse_card_sentence("합성 설문 기준 '라벨' 영역 — 순위 표기가 없는 문장입니다. ▸ 산출물(FAQ 초안): 본문")
    assert parsed["card_kind"] == "area" and parsed["rank_label"] is None


# ---------- 리포트 안내 문구 ----------
def test_rank_notice_texts():
    all_joint = ["공동 1순위"] * 3
    assert cards.rank_notice(all_joint, 100, 1) == (
        "합성 설문(응답 100건)에서는 상위 영역의 선택 비율 차이가 우연 범위라 순위를 가리지 못했습니다. 다음 회차 문항 1번(영역별 눈금)으로 순위를 가립니다.")
    assert cards.rank_notice(all_joint, 100, None) == "합성 설문(응답 100건)에서는 상위 영역의 선택 비율 차이가 우연 범위라 순위를 가리지 못했습니다."
    assert cards.rank_notice(["공동 1순위", "공동 1순위", "3순위"], 100, 1) == "일부 영역은 차이가 우연 범위라 공동 순위로 표시했습니다."
    assert cards.rank_notice(["1순위", "공동 2순위", "공동 2순위"], 100, 1) == "일부 영역은 차이가 우연 범위라 공동 순위로 표시했습니다."
    assert cards.rank_notice(["1순위", "2순위", "3순위"], 100, 1) is None
    assert cards.rank_notice([], 100, 1) is None  # 영역 카드가 없다
    assert cards.rank_notice([None, None], 100, 1) is None  # 순위 라벨을 못 읽으면 안내하지 않는다
