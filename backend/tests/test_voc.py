"""A-3의 voc 부분. 임시 SQLite만 쓰고 모든 값은 가짜다. 리뷰 본문은 만들지 않는다(제목·본문 존재 여부만 쓴다)."""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import get_session
from app.main import app
from app.models import AdJudgement, PipelineRun, Product, ProductFamily, Review, Round
from app.services.voc import voc_section

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


def add_review(session, review_id, product, rating, day, has_text=True):
    session.add(
        Review(
            review_id=review_id, product_name=product, rating=rating, date=day, helpful_count=0,
            title="제목" if has_text else None, review_text=None,
        )
    )


def add_run(session, round_id):
    run = PipelineRun(round_id=round_id, step="ad-judgement", status="succeeded", counters={}, started_at=T0)
    session.add(run)
    session.flush()
    return run.run_id


def judge(session, review_id, run_id, weight, status="ok", minutes=0):
    ok = status == "ok"
    session.add(
        AdJudgement(
            review_id=review_id, run_id=run_id, status=status,
            ad_probability=round(1 - weight, 6) if ok else None, ad_weight=weight if ok else None,
            judged_at=T0 + timedelta(minutes=minutes),
        )
    )


@pytest.fixture
def api(session):
    pilot = Round(label="[파일럿-임시] 2026-11-02")
    q1 = Round(label="2026-Q1", period_start=date(2026, 1, 1), period_end=date(2026, 3, 31))
    q2 = Round(label="2026-Q2", period_start=date(2026, 4, 1), period_end=date(2026, 6, 30))
    session.add_all([pilot, q1, q2, ProductFamily(name="가"), ProductFamily(name="나")])
    session.flush()
    session.add_all([Product(product_name="pA", family_id=1), Product(product_name="pB", family_id=2)])
    session.flush()
    run1, run2 = add_run(session, pilot.round_id), add_run(session, q1.round_id)
    # 제품군 가
    add_review(session, 1, "pA", 5, date(2026, 1, 1))   # period_start 정확히: 포함, 하한 아래 가중치
    add_review(session, 2, "pA", 3, date(2026, 3, 31))  # period_end 정확히: 포함
    add_review(session, 3, "pA", 4, date(2026, 2, 10))  # 이전 실행 성공 + 최신 실행 실패
    add_review(session, 4, "pA", 2, date(2026, 2, 11))  # 실패만 있음
    add_review(session, 5, "pA", 5, date(2026, 2, 12))  # 판정 없음
    add_review(session, 6, "pA", 5, date(2026, 2, 13), has_text=False)  # 제목·본문 없음
    add_review(session, 7, "pA", 5, date(2025, 12, 31))  # 어느 회차에도 속하지 않음
    add_review(session, 8, "pA", 4, date(2026, 4, 1))   # 다른 회차(2026-Q2)
    add_review(session, 9, "pA", 1, date(2026, 1, 15))  # 성공 판정 두 번: 최신이 쓰인다
    add_review(session, 10, "pA", 4, date(2026, 5, 5))  # 다른 회차
    # 제품군 나
    add_review(session, 11, "pB", 5, date(2026, 2, 1))
    session.flush()
    judge(session, 1, run1, 0.02)
    judge(session, 2, run1, 0.8)
    judge(session, 3, run1, 0.5, minutes=0)
    judge(session, 3, run2, 0.0, status="failed", minutes=10)
    judge(session, 4, run2, 0.0, status="failed", minutes=10)
    judge(session, 9, run1, 0.9, minutes=0)
    judge(session, 9, run2, 0.3, minutes=20)
    judge(session, 8, run1, 1.0)
    judge(session, 11, run1, 1.0)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    client.q1, client.q2 = q1.round_id, q2.round_id
    yield client
    app.dependency_overrides.clear()


def voc(api, family, round_id):
    response = api.get(f"/api/families/{family}/dashboard?round_id={round_id}")
    assert response.status_code == 200
    return response.json()["voc"]


def dist(cells):
    return {c["rating"]: c["count"] for c in cells}


def test_buckets_and_total_identity(api):
    v = voc(api, 1, api.q1)
    assert v["counts"] == {"total": 7, "judged": 4, "unjudged": 2, "no_text": 1}
    assert v["counts"]["total"] == v["counts"]["judged"] + v["counts"]["unjudged"] + v["counts"]["no_text"]


def test_boundary_dates_are_included_and_outside_dates_are_excluded(api):
    v = voc(api, 1, api.q1)
    # 1월 1일(period_start)과 3월 31일(period_end)의 글이 판정 묶음에 들어 있다
    assert dist(v["unweighted"]["rating_distribution"])[5] == 1 and dist(v["unweighted"]["rating_distribution"])[3] == 1
    assert v["excluded"] == {"count": 3, "other_round_count": 2, "outside_rounds_count": 1}
    q2 = voc(api, 1, api.q2)
    assert q2["counts"]["total"] == 2 and q2["excluded"] == {"count": 8, "other_round_count": 7, "outside_rounds_count": 1}


def test_unweighted_aggregate(api):
    u = voc(api, 1, api.q1)["unweighted"]
    assert u["count"] == 4 and u["mean_rating"] == 3.25
    assert dist(u["rating_distribution"]) == {1: 1, 2: 0, 3: 1, 4: 1, 5: 1}


def test_weighted_aggregate_applies_the_floor_and_the_latest_ok_judgement(api):
    v = voc(api, 1, api.q1)
    w = v["weighted"]
    # 가중치: 글1 max(0.1, 0.02)=0.1, 글2 0.8, 글3 0.5(최신 실행은 실패라 이전 성공 판정), 글9 0.3(최신 성공 판정)
    assert v["weight_floor"] == 0.1
    assert w["count"] == 1.7
    assert w["mean_rating"] == round((0.1 * 5 + 0.8 * 3 + 0.5 * 4 + 0.3 * 1) / 1.7, 4) == 3.0588
    assert dist(w["rating_distribution"]) == {1: 0.3, 2: 0.0, 3: 0.8, 4: 0.5, 5: 0.1}


def test_stored_ad_weight_is_not_changed_by_aggregation(api, session):
    voc(api, 1, api.q1)
    stored = session.scalar(select(AdJudgement.ad_weight).where(AdJudgement.review_id == 1))
    assert stored == 0.02


def test_failed_only_review_is_unjudged_and_counted_as_failed(api):
    u = voc(api, 1, api.q1)["unjudged"]
    assert u["count"] == 2 and u["failed_count"] == 1
    assert dist(u["rating_distribution"]) == {1: 0, 2: 1, 3: 0, 4: 0, 5: 1}


def test_no_text_bucket(api):
    n = voc(api, 1, api.q1)["no_text"]
    assert n["count"] == 1 and dist(n["rating_distribution"]) == {1: 0, 2: 0, 3: 0, 4: 0, 5: 1}


def test_unjudged_and_no_text_do_not_depend_on_the_toggle_inputs(api):
    # 토글은 화면에서만 바뀐다. 응답은 항상 가중과 비가중을 둘 다 담고 두 묶음은 같은 값이다.
    first, second = voc(api, 1, api.q1), voc(api, 1, api.q1)
    assert first == second and {"unweighted", "weighted", "unjudged", "no_text"} <= set(first)


def test_family_filter(api):
    a, b = voc(api, 1, api.q1), voc(api, 2, api.q1)
    assert b["counts"] == {"total": 1, "judged": 1, "unjudged": 0, "no_text": 0}
    assert b["unweighted"]["mean_rating"] == 5.0 and b["weighted"]["count"] == 1.0
    assert a != b and b["excluded"]["count"] == 0


def test_small_sample_flag_uses_the_threshold(api, session):
    v = voc(api, 1, api.q1)
    assert v["small_sample_threshold"] == 30 and v["small_sample"] is True
    q1 = session.get(Round, api.q1)
    at_limit = voc_section(session, 1, q1, weight_floor=0.1, small_sample_threshold=4)
    below = voc_section(session, 1, q1, weight_floor=0.1, small_sample_threshold=5)
    assert at_limit["small_sample"] is False and below["small_sample"] is True


def test_zero_floor_uses_the_stored_weight(api, session):
    q1 = session.get(Round, api.q1)
    v = voc_section(session, 1, q1, weight_floor=0.0, small_sample_threshold=30)
    assert v["weighted"]["count"] == round(0.02 + 0.8 + 0.5 + 0.3, 4)


def test_empty_judged_bucket_has_no_mean(api, session):
    # 제품군 나의 2026-Q2: 리뷰 없음
    v = voc(api, 2, api.q2)
    assert v["counts"] == {"total": 0, "judged": 0, "unjudged": 0, "no_text": 0}
    assert v["unweighted"]["mean_rating"] is None and v["weighted"]["mean_rating"] is None and v["weighted"]["count"] == 0.0


def test_survey_section_is_unchanged_by_voc(api, session):
    from app.services.dashboard import survey_section

    body = api.get(f"/api/families/1/dashboard?round_id={api.q1}").json()
    assert body["survey"] == survey_section(session, api.q1)


def test_weight_floor_setting(monkeypatch):
    monkeypatch.delenv("AD_WEIGHT_FLOOR", raising=False)
    assert get_settings().ad_weight_floor == 0.1
    monkeypatch.setenv("AD_WEIGHT_FLOOR", "0.25")
    assert get_settings().ad_weight_floor == 0.25
    monkeypatch.setenv("AD_WEIGHT_FLOOR", "0")
    assert get_settings().ad_weight_floor == 0.0
    for bad in ("1", "-0.1", "abc", "nan"):
        monkeypatch.setenv("AD_WEIGHT_FLOOR", bad)
        with pytest.raises(RuntimeError) as error:
            get_settings()
        assert "AD_WEIGHT_FLOOR" in str(error.value)
        if bad != "1":  # 오류 메시지에는 값이 아니라 이름만 있다("1"은 안내 문구의 '1 미만'과 겹친다)
            assert bad not in str(error.value)


def _api_with_judged(session, count):
    """제품군 하나에 2026-Q1 안의 판정된 글을 count건 만든 API 클라이언트."""
    q1 = Round(label="2026-Q1", period_start=date(2026, 1, 1), period_end=date(2026, 3, 31))
    session.add_all([q1, ProductFamily(name="가")])
    session.flush()
    session.add(Product(product_name="pA", family_id=1))
    session.flush()
    run = add_run(session, q1.round_id)
    for review_id in range(1, count + 1):
        add_review(session, review_id, "pA", 5, date(2026, 2, 1))
    session.flush()
    for review_id in range(1, count + 1):
        judge(session, review_id, run, 1.0)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    client.q1 = q1.round_id
    return client


def test_small_sample_badge_boundary_is_below_thirty(session):
    # 결정: 판정 n이 30건 미만이면 "표본 적음". 29건이면 있고 30건이면 없다.
    try:
        from app.config import VOC_SMALL_SAMPLE_THRESHOLD

        assert VOC_SMALL_SAMPLE_THRESHOLD == 30
        api = _api_with_judged(session, 29)
        v = voc(api, 1, api.q1)
        assert v["counts"]["judged"] == 29 and v["small_sample"] is True
        add_review(session, 30, "pA", 5, date(2026, 2, 1))
        session.flush()
        judge(session, 30, session.scalar(select(PipelineRun.run_id)), 1.0)
        session.commit()
        v = voc(api, 1, api.q1)
        assert v["counts"]["judged"] == 30 and v["small_sample"] is False
    finally:
        app.dependency_overrides.clear()
