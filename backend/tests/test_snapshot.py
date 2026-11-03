"""분석 스냅샷(step analysis-snapshot). 임시 SQLite만 쓰고 모든 값은 가짜다. LLM은 쓰지 않는다."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import AdJudgement, AnalysisSnapshot, PipelineRun, Product, ProductFamily, Review, Round
from app.services.dashboard import survey_section
from app.services.snapshot import compute_snapshot
from app.services.survey_load import load_synthetic_survey
from app.services.synthetic_survey import generate
from app.services.voc import voc_section

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


def add_review(session, review_id, product, rating, day, has_text=True):
    session.add(
        Review(
            review_id=review_id, product_name=product, rating=rating, date=day, helpful_count=0,
            title="제목" if has_text else None, review_text=None,
        )
    )


def judge(session, review_id, run_id, weight, status="ok"):
    ok = status == "ok"
    session.add(
        AdJudgement(
            review_id=review_id, run_id=run_id, status=status,
            ad_probability=round(1 - weight, 6) if ok else None, ad_weight=weight if ok else None, judged_at=T0,
        )
    )


@pytest.fixture
def world(session):
    session.add_all([ProductFamily(name="일회용 카메라"), ProductFamily(name="인스탁스 즉석카메라")])
    session.add(Round(label="[파일럿-임시] 2026-11-02"))
    session.commit()
    load_synthetic_survey(session, generate())
    session.add_all([Product(product_name="pA", family_id=1), Product(product_name="pB", family_id=2)])
    session.flush()
    q1 = session.scalar(select(Round).where(Round.label == "2026-Q1"))
    run = PipelineRun(round_id=q1.round_id, step="ad-judgement", status="succeeded", counters={}, started_at=T0)
    session.add(run)
    session.flush()
    add_review(session, 1, "pA", 5, date(2026, 1, 1))
    add_review(session, 2, "pA", 3, date(2026, 3, 31))
    add_review(session, 3, "pA", 4, date(2026, 2, 10))
    add_review(session, 4, "pA", 2, date(2026, 2, 11))
    add_review(session, 5, "pA", 5, date(2026, 2, 12), has_text=False)
    add_review(session, 6, "pB", 5, date(2026, 2, 1))
    session.flush()
    judge(session, 1, run.run_id, 0.02)
    judge(session, 2, run.run_id, 0.8)
    judge(session, 3, run.run_id, 0.0, status="failed")
    judge(session, 6, run.run_id, 1.0)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    client.q1 = q1
    client.session = session
    yield client
    app.dependency_overrides.clear()


def snapshot(session, family_id, q1):
    family = session.get(ProductFamily, family_id)
    return compute_snapshot(session, family, q1, weight_floor=0.1, small_sample_threshold=30)


def by_id(table):
    return {r["row_id"]: r for r in table["rows"]}


def test_same_input_gives_identical_table_and_evidence(world):
    first = snapshot(world.session, 1, world.q1)
    second = snapshot(world.session, 1, world.q1)
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == json.dumps(second, sort_keys=True, ensure_ascii=False)


def test_survey_rows_match_the_dashboard_counts_and_evidence_sizes(world):
    table, evidence = snapshot(world.session, 1, world.q1)
    rows = by_id(table)
    survey = survey_section(world.session, world.q1.round_id)
    assert rows["survey:respondents"]["metrics"] == {"응답자 수": 100}
    assert len(evidence["survey:respondents"]["ids"]) == 100 and evidence["survey:respondents"]["kind"] == "survey"
    option_rows = [r for r in table["rows"] if r["row_id"].startswith("survey:q")]
    assert len(option_rows) == 47  # 문항 10개의 선택지 합(5+5+5+5+5+5+5+5+2+5 = 47)
    for question in survey["questions"]:
        code = f"q{question['question_id'] - min(q['question_id'] for q in survey['questions']) + 1:02d}"
        for result in question["results"]:
            row = rows[f"survey:{code}:{result['code']}"]
            assert row["metrics"]["응답 수"] == result["count"]
            assert row["metrics"]["비율(%)"] == round(result["count"] / 100 * 100, 1)
            assert len(evidence[row["row_id"]]["ids"]) == result["count"]  # 허용 목록의 크기 = 집계 건수
            assert row["source"] == "합성" and evidence[row["row_id"]]["kind"] == "survey"


def test_voc_rows_match_the_dashboard_and_evidence_sizes(world):
    table, evidence = snapshot(world.session, 1, world.q1)
    rows = by_id(table)
    voc = voc_section(world.session, 1, world.q1, weight_floor=0.1, small_sample_threshold=30)
    c = voc["counts"]
    assert (c["total"], c["judged"], c["unjudged"], c["no_text"]) == (5, 2, 2, 1)
    assert rows["voc:total:count"]["metrics"] == {"리뷰 수": 5} and len(evidence["voc:total:count"]["ids"]) == 5
    assert rows["voc:judged:count"]["metrics"]["건수"] == 2 and len(evidence["voc:judged:count"]["ids"]) == 2
    assert rows["voc:unjudged:count"]["metrics"] == {"건수": 2, "판정 실패 건수": 1}
    assert len(evidence["voc:unjudged:count"]["ids"]) == 2
    assert rows["voc:no_text:count"]["metrics"]["건수"] == 1
    assert rows["voc:judged:mean_unweighted"]["metrics"]["평균 평점"] == voc["unweighted"]["mean_rating"] == 4.0
    assert rows["voc:judged:mean_weighted"]["metrics"] == {"가중 평균 평점": voc["weighted"]["mean_rating"], "가중치 하한": 0.1}
    assert rows["voc:judged:count_weighted"]["metrics"]["가중 건수"] == voc["weighted"]["count"] == 0.9
    for rating in range(1, 6):
        assert rows[f"voc:judged:dist_unweighted:{rating}"]["metrics"]["평점"] == rating
        assert f"voc:judged:dist_weighted:{rating}" in rows
    assert all(row["source"] == "실측" for row in table["rows"] if row["group"] == "VOC")
    assert all(evidence[r["row_id"]]["kind"] == "review" for r in table["rows"] if r["group"] == "VOC")


def test_small_sample_flag_is_set_only_on_judged_group_rows(world):
    table, _ = snapshot(world.session, 1, world.q1)
    flagged = {r["row_id"] for r in table["rows"] if r["small_sample"]}
    assert flagged and all(row_id.startswith("voc:judged:") for row_id in flagged)
    assert "voc:unjudged:count" not in flagged and "voc:total:count" not in flagged


def test_family_filter_changes_voc_but_not_survey(world):
    a, _ = snapshot(world.session, 1, world.q1)
    b, _ = snapshot(world.session, 2, world.q1)
    ra, rb = by_id(a), by_id(b)
    assert ra["voc:total:count"]["metrics"] != rb["voc:total:count"]["metrics"]
    assert [r for r in a["rows"] if r["group"] == "설문"] == [r for r in b["rows"] if r["group"] == "설문"]


def test_table_contains_no_review_text_or_author_keys(world):
    table, _ = snapshot(world.session, 1, world.q1)
    text = json.dumps(table, ensure_ascii=False)
    for forbidden in ("author", "review_text", "variant", "title"):
        assert forbidden not in text


def test_step_creates_run_and_snapshot_and_stacks_on_rerun(world):
    for expected in (1, 2):
        response = world.post(f"/api/rounds/{world.q1.round_id}/pipeline/analysis-snapshot", json={"family_id": 1})
        assert response.status_code == 201
        body = response.json()
        assert body["step"] == "analysis-snapshot" and body["status"] == "succeeded"
        assert len(world.session.scalars(select(AnalysisSnapshot)).all()) == expected
    run = world.session.get(PipelineRun, body["run_id"])
    assert run.family_id == 1 and run.counters["rows"] > 0
    snap = world.session.scalars(select(AnalysisSnapshot).order_by(AnalysisSnapshot.snapshot_id.desc())).first()
    assert snap.run_id == body["run_id"] and snap.round_id == world.q1.round_id and snap.family_id == 1
    detail = world.get(f"/api/runs/{body['run_id']}").json()
    assert detail["counters"]["rows"] == len(snap.table_json["rows"]) and detail["counters"]["voc_rows"] > 0


def test_step_errors(world):
    q1 = world.q1.round_id
    pilot = world.session.scalar(select(Round.round_id).where(Round.label.like("[파일럿-임시]%")))
    assert world.post(f"/api/rounds/{q1}/pipeline/analysis-snapshot", json={"family_id": 99}).json()["error"]["code"] == "NOT_FOUND"
    assert world.post("/api/rounds/999/pipeline/analysis-snapshot", json={"family_id": 1}).status_code == 404
    assert world.post(f"/api/rounds/{pilot}/pipeline/analysis-snapshot", json={"family_id": 1}).status_code == 404
    missing = world.post(f"/api/rounds/{q1}/pipeline/analysis-snapshot", json={})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "VALIDATION_ERROR"
    assert world.post(f"/api/rounds/{q1}/pipeline/nothing", json={"family_id": 1}).json()["error"]["code"] == "BAD_REQUEST"
    assert world.post(f"/api/rounds/{q1}/pipeline/next-survey-draft", json={"family_id": 1}).status_code == 400
    assert world.session.scalars(select(AnalysisSnapshot)).all() == []
