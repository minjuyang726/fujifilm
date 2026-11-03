"""가설 규칙 R1~R4(DB 없이 손으로 만든 표로 시험한다). 모든 값은 가짜다."""

import pytest

from app.services import hypotheses as h

Q = {
    "q01": ("전반 만족도는?", ["매우 불만족", "불만족", "보통", "만족", "매우 만족"]),
    "q03": ("사용하기 쉬웠나요?", ["매우 어려웠다", "어려웠다", "보통이다", "쉬웠다", "매우 쉬웠다"]),
    "q06": ("주로 언제 썼나요?", ["여행", "모임·행사", "선물", "일상 기록", "기타"]),
    "q08": ("개선할 점을 골라 주세요.", ["비용", "대기", "사용법", "품질", "없음"]),
    "q09": ("추천한 적이 있나요?", ["예", "아니오"]),
}
TYPES = {"q01": "scale5", "q03": "scale5", "q06": "single", "q08": "multi", "q09": "single"}


def make_table(percentages: dict, judged_n=4, mean=4.5, small=True, n=100):
    """percentages: {문항코드: [선택지별 비율(%)]}. 나머지 문항은 균등하지 않은 값으로 채운다. n은 응답자 수이고 응답 수는 비율 x n / 100이다."""
    rows = [{"row_id": "survey:respondents", "group": "설문", "source": "합성", "item": "설문 응답자 수", "metrics": {"응답자 수": n}, "small_sample": False}]
    for code, (text, labels) in Q.items():
        values = percentages.get(code) or [round(100 / len(labels) + (i * 7 - 10), 1) for i in range(len(labels))]
        for index, (label, pct) in enumerate(zip(labels, values), start=1):
            rows.append(
                {"row_id": f"survey:{code}:{index}", "group": "설문", "source": "합성", "item": f"{text} — {label}",
                 "metrics": {"응답 수": round(pct * n / 100), "비율(%)": pct, "선택지 번호": index}, "small_sample": False}
            )
    rows.append({"row_id": "voc:judged:count", "group": "VOC", "source": "실측", "item": "판정 묶음",
                 "metrics": {"건수": judged_n, "표본 적음 기준(건)": 30}, "small_sample": small})
    if judged_n:
        rows.append({"row_id": "voc:judged:mean_unweighted", "group": "VOC", "source": "실측", "item": "판정 묶음 평균 평점(비가중)",
                     "metrics": {"평균 평점": mean}, "small_sample": small})
    return {"family": "가", "round": "2026-Q1", "rows": rows}


# 선택지 비율이 서로 충분히 달라서 R2(R2′)가 걸리지 않는 기본값(n=100에서 q06 격차 40%p, q09 격차 40%p)
SPREAD = {"q06": [60.0, 20.0, 10.0, 5.0, 5.0], "q09": [70.0, 30.0], "q01": [2.0, 4.0, 20.0, 40.0, 34.0]}


def find(table, types=TYPES):
    return h.find_hypotheses(table, types)


def rules(result):
    return [item["rule"] for item in result]


# ---------- R1 ----------
def test_r1_small_sample_triggers_and_mentions_sample_word():
    result = find(make_table(SPREAD, judged_n=4))
    r1 = [x for x in result if x["rule"] == "R1"]
    assert len(r1) == 1 and r1[0]["kind"] == "uncertain" and r1[0]["related_row_ids"] == ["voc:judged:count"]
    assert "표본" in r1[0]["statement"] and "4건" in r1[0]["statement"] and "30건" in r1[0]["statement"]


def test_r1_not_triggered_when_not_a_small_sample():
    assert "R1" not in rules(find(make_table(SPREAD, judged_n=30, small=False)))


# ---------- R2′ ----------
# 격차 <= 1.96 x SE, SE = sqrt((p1 + p2 - (p1 - p2)^2) / n). n = 100에서 손으로 계산한 임계(%p):
#   (32, 19): SE 계산 임계 13.763 -> 격차 13 걸림 / (32, 18): 임계 13.585 -> 격차 14 안 걸림
def test_r2_prime_gap_just_below_and_just_above_the_critical_value():
    below = find(make_table({**SPREAD, "q06": [32.0, 19.0, 19.0, 15.0, 15.0]}))  # 격차 13.0 <= 13.763
    assert "R2" in rules(below)
    above = find(make_table({**SPREAD, "q06": [32.0, 18.0, 17.0, 17.0, 16.0]}))  # 격차 14.0 > 13.585
    assert "R2" not in rules(above)


def test_r2_prime_boundary_is_inclusive(monkeypatch):
    monkeypatch.setattr(h, "R2_Z", 0.0)  # 임계 0 -> 격차 0(공동 1위)만 경계에서 걸린다
    tie = find(make_table({**SPREAD, "q06": [30.0, 30.0, 20.0, 10.0, 10.0]}))
    assert "R2" in rules(tie)
    one_point = find(make_table({**SPREAD, "q06": [30.0, 29.0, 21.0, 10.0, 10.0]}))
    assert "R2" not in rules(one_point)


def test_r2_prime_critical_value_matches_the_formula():
    gap, critical, uncertain = h.r2_test(32.0, 19.0, 100)
    assert gap == 13.0 and uncertain
    assert critical == pytest.approx(1.96 * ((0.32 + 0.19 - 0.13 ** 2) / 100) ** 0.5 * 100)
    assert critical == pytest.approx(13.7633, abs=1e-3)


def test_r2_prime_depends_on_the_number_of_responses():
    same_percentages = {**SPREAD, "q06": [30.0, 25.0, 20.0, 15.0, 10.0]}  # 격차 5.0
    assert "R2" in rules(find(make_table(same_percentages, n=100)))  # 임계 14.5
    assert "R2" not in rules(find(make_table(same_percentages, n=1000)))  # 임계 4.59 -> 같은 비율이라도 응답이 많으면 안 걸린다


def test_r2_prime_still_catches_what_the_old_fixed_gap_caught():
    for gap_case in ([30.0, 25.0, 20.0, 15.0, 10.0], [30.0, 28.0, 20.0, 12.0, 10.0], [30.0, 30.0, 20.0, 10.0, 10.0]):  # 격차 5.0, 2.0, 0.0
        assert "R2" in rules(find(make_table({**SPREAD, "q06": gap_case})))


def test_r2_prime_catches_gaps_larger_than_the_old_five_points():
    # 격차 10.0%p: 이전 고정 기준(5%p)은 놓치고 R2′(임계 13.72)는 잡는다
    assert "R2" in rules(find(make_table({**SPREAD, "q06": [30.0, 20.0, 20.0, 15.0, 15.0]})))


def test_r2_only_looks_at_single_questions():
    close = [20.0, 20.0, 20.0, 20.0, 20.0]
    table = make_table({**SPREAD, "q03": close, "q08": close})  # scale5, multi는 뺀다
    assert "R2" not in rules(find(table))
    assert "R2" in rules(find(make_table({**SPREAD, "q06": close})))


def test_r2_statement_and_rows_and_sorting_by_gap():
    table = make_table({**SPREAD, "q06": [30.0, 28.0, 20.0, 12.0, 10.0], "q09": [50.5, 49.5]})
    result = [x for x in find(table) if x["rule"] == "R2"]
    # 차이가 작은 순: q09(1.0%p) 다음 q06(2.0%p)
    assert [x["related_row_ids"] for x in result] == [["survey:q09:1", "survey:q09:2"], ["survey:q06:1", "survey:q06:2"]]
    assert "합성" in result[0]["statement"] and "1.0%p" in result[0]["statement"] and "2.0%p" in result[1]["statement"]
    assert all(x["kind"] == "uncertain" for x in result)


def test_r2_ties_in_gap_are_ordered_by_question_code():
    table = make_table({**SPREAD, "q06": [30.0, 28.0, 20.0, 12.0, 10.0], "q09": [51.0, 49.0]})  # 둘 다 2.0%p
    result = [x for x in find(table) if x["rule"] == "R2"]
    assert [x["related_row_ids"][0] for x in result] == ["survey:q06:1", "survey:q09:1"]


def test_r2_tie_for_first_place_has_zero_gap():
    result = [x for x in find(make_table({**SPREAD, "q06": [30.0, 30.0, 20.0, 10.0, 10.0]})) if x["rule"] == "R2"]
    assert result and "0.0%p" in result[0]["statement"]


# ---------- R3 ----------
def test_r3_boundaries():
    exact = find(make_table({**SPREAD, "q01": [5.0, 5.0, 30.0, 30.0, 30.0], "q09": [50.0, 50.0]}))  # 만족 합 60.0, 아니오 50.0
    assert "R3" in rules(exact)
    below_sat = find(make_table({**SPREAD, "q01": [5.0, 5.1, 30.0, 29.9, 30.0], "q09": [50.0, 50.0]}))  # 만족 합 59.9
    assert "R3" not in rules(below_sat)
    below_no = find(make_table({**SPREAD, "q01": [5.0, 5.0, 30.0, 30.0, 30.0], "q09": [50.1, 49.9]}))  # 아니오 49.9
    assert "R3" not in rules(below_no)


def test_r3_statement_related_rows_and_priority_first():
    table = make_table({**SPREAD, "q01": [2.0, 3.0, 25.0, 40.0, 30.0], "q09": [40.0, 60.0], "q06": [30.0, 28.0, 20.0, 12.0, 10.0]})
    result = find(table)
    assert rules(result)[0] == "R3" and result[0]["kind"] == "contradictory"
    assert result[0]["related_row_ids"] == ["survey:q01:4", "survey:q01:5", "survey:q09:2"]
    assert "합성" in result[0]["statement"] and "70.0%" in result[0]["statement"] and "60.0%" in result[0]["statement"]


# ---------- R4 ----------
def test_r4_high_satisfaction_with_low_voc_mean_and_inverse():
    high_sat = {**SPREAD, "q01": [1.0, 2.0, 17.0, 40.0, 40.0], "q09": [90.0, 10.0]}  # 만족 80, 추천 안 함 10 -> R3 아님
    assert "R4" in rules(find(make_table(high_sat, mean=3.5)))  # 경계 포함
    assert "R4" not in rules(find(make_table(high_sat, mean=3.6)))
    low_sat = {**SPREAD, "q01": [10.0, 10.0, 31.0, 25.0, 24.0], "q09": [90.0, 10.0]}  # 만족 49
    assert "R4" in rules(find(make_table(low_sat, mean=4.5)))
    assert "R4" not in rules(find(make_table(low_sat, mean=4.4)))


def test_r4_needs_judged_items_and_mentions_sample_word_when_small():
    high_sat = {**SPREAD, "q01": [1.0, 2.0, 17.0, 40.0, 40.0], "q09": [90.0, 10.0]}
    assert "R4" not in rules(find(make_table(high_sat, judged_n=0, mean=1.0)))
    r4 = [x for x in find(make_table(high_sat, mean=3.0, small=True)) if x["rule"] == "R4"][0]
    assert r4["kind"] == "contradictory" and "합성" in r4["statement"] and "표본" in r4["statement"]
    assert "voc:judged:count" in r4["related_row_ids"]
    r4_big = [x for x in find(make_table(high_sat, judged_n=40, mean=3.0, small=False)) if x["rule"] == "R4"][0]
    assert "표본" not in r4_big["statement"]


def test_r4_is_not_triggered_by_the_typical_current_data_shape():
    # 만족 67%, VOC 평균 4.29 / 만족 75%, 평균 5.0: 현재 데이터와 비슷한 값은 R4에 걸리지 않는다
    assert "R4" not in rules(find(make_table({**SPREAD, "q01": [2.0, 4.0, 27.0, 39.0, 28.0]}, mean=4.2857)))
    assert "R4" not in rules(find(make_table({**SPREAD, "q01": [3.0, 6.0, 17.0, 42.0, 32.0]}, mean=5.0)))


# ---------- 순서·상한·재현성 ----------
def test_priority_order_and_cap_of_five():
    close = [20.0, 20.0, 20.0, 20.0, 20.0]
    all_single = {"q01": "single", "q03": "single", "q06": "single", "q08": "single", "q09": "single"}
    table = make_table({"q01": close, "q03": close, "q06": close, "q08": close, "q09": [50.0, 50.0]}, mean=4.0)
    result = h.find_hypotheses(table, all_single)
    assert len(result) == h.MAX_HYPOTHESES == 5
    # R2가 5개 모두 걸리면 R1은 상한에 밀려 빠진다. 차이가 같으면 문항 코드 순서다.
    assert rules(result) == ["R2"] * 5
    assert [x["related_row_ids"][0].split(":")[1] for x in result] == ["q01", "q03", "q06", "q08", "q09"]


def test_contradictory_comes_before_uncertain_within_the_cap():
    table = make_table({**SPREAD, "q01": [2.0, 3.0, 25.0, 40.0, 30.0], "q09": [40.0, 60.0], "q06": [30.0, 28.0, 20.0, 12.0, 10.0]})
    assert rules(find(table)) == ["R3", "R2", "R1"]


def test_r1_comes_last_and_result_is_deterministic():
    table = make_table(SPREAD)
    assert find(table) == find(table)
    assert rules(find(make_table({**SPREAD, "q06": [30.0, 28.0, 20.0, 12.0, 10.0]})))[-1] == "R1"


def test_unknown_question_types_are_skipped():
    close = [20.0, 20.0, 20.0, 20.0, 20.0]
    assert "R2" not in rules(find(make_table({**SPREAD, "q06": close}), types={}))


def test_statements_have_required_marker_words():
    for item in find(make_table({**SPREAD, "q06": [30.0, 28.0, 20.0, 12.0, 10.0]})):
        if item["rule"] in ("R2", "R3", "R4"):
            assert "합성" in item["statement"]
        if item["rule"] == "R1":
            assert "표본" in item["statement"]
        assert item["kind"] in ("uncertain", "contradictory") and item["related_row_ids"]
