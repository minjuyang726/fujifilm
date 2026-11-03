"""A-10(제안 근거 목록)과 A-4 survey. 임시 SQLite만 쓰고 모든 값은 가짜다."""

import json
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import (
    ActionSuggestion, AnalysisSnapshot, PipelineRun, Product, ProductFamily, Report, Review, Round, SurveyResponse,
)
from app.services.evidence import evidence_by_kind, evidence_counts
from app.services.survey_load import load_synthetic_survey
from app.services.synthetic_survey import generate

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
SECRET = "가짜본문-응답에-나오면-안-됨"


@pytest.fixture
def world(session):
    session.add(ProductFamily(name="가"))
    session.commit()
    load_synthetic_survey(session, generate())
    session.add(Product(product_name="pA", family_id=1))
    session.flush()
    q1 = session.scalar(select(Round).where(Round.label == "2026-Q1"))
    for review_id in range(1, 121):  # 허용 목록 120건 (쪽 나누기 확인용)
        session.add(
            Review(review_id=review_id, product_name="pA", rating=1 + review_id % 5, date=date(2026, 2, 1), helpful_count=0,
                   title="제목", review_text=SECRET, variant="변형값")
        )
    session.flush()
    run = PipelineRun(round_id=q1.round_id, step="analysis-snapshot", status="succeeded", counters={}, started_at=T0)
    session.add(run)
    session.flush()
    response_ids = sorted(session.scalars(select(SurveyResponse.response_id).where(SurveyResponse.round_id == q1.round_id)))
    allowed = {
        "voc:judged:count": {"kind": "review", "ids": list(range(1, 121))},
        "voc:total:count": {"kind": "review", "ids": list(range(1, 121))},
        "survey:q09:1": {"kind": "survey", "ids": response_ids[:7]},
        "survey:respondents": {"kind": "survey", "ids": response_ids},
        "voc:unjudged:count": {"kind": "review", "ids": []},
    }
    snapshot = AnalysisSnapshot(
        run_id=run.run_id, round_id=q1.round_id, family_id=1, table_json={"rows": []}, allowed_evidence_json=allowed, computed_at=T0
    )
    report = Report(round_id=q1.round_id, family_id=1, run_id=run.run_id, generated_at=T0)
    session.add_all([snapshot, report])
    session.flush()
    suggestions = {
        "mixed": ActionSuggestion(report_id=report.report_id, snapshot_id=snapshot.snapshot_id, order_no=1, sentence="x", row_ids=["voc:judged:count", "survey:q09:1"]),
        "reviews": ActionSuggestion(report_id=report.report_id, snapshot_id=snapshot.snapshot_id, order_no=2, sentence="y", row_ids=["voc:judged:count", "voc:total:count"]),
        "empty": ActionSuggestion(report_id=report.report_id, snapshot_id=snapshot.snapshot_id, order_no=3, sentence="z", row_ids=["voc:unjudged:count"]),
    }
    session.add_all(suggestions.values())
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    client.s = suggestions
    client.snapshot = snapshot
    client.response_ids = response_ids
    yield client
    app.dependency_overrides.clear()


def test_union_of_rows_dedupes_ids_and_total_matches_counts(world):
    sid = world.s["reviews"].suggestion_id
    body = world.get(f"/api/suggestions/{sid}/evidence").json()
    assert body["total"] == 120 == evidence_counts(world.snapshot, ["voc:judged:count", "voc:total:count"])["review"]
    mixed = world.s["mixed"].suggestion_id
    body = world.get(f"/api/suggestions/{mixed}/evidence?page_size=200").json()
    assert body["total"] == 127 and len(body["items"]) == 127
    counts = evidence_counts(world.snapshot, ["voc:judged:count", "survey:q09:1"])
    assert counts == {"review": 120, "survey": 7}


def test_pagination_default_50_and_pages_are_disjoint_and_sorted(world):
    sid = world.s["reviews"].suggestion_id
    pages = [world.get(f"/api/suggestions/{sid}/evidence?page={n}").json() for n in (1, 2, 3, 4)]
    assert [len(p["items"]) for p in pages] == [50, 50, 20, 0]
    assert all(p["page_size"] == 50 and p["total"] == 120 for p in pages)
    ids = [item["evidence_id"] for p in pages for item in p["items"]]
    assert ids == list(range(1, 121))
    custom = world.get(f"/api/suggestions/{sid}/evidence?page=2&page_size=100").json()
    assert len(custom["items"]) == 20 and custom["page_size"] == 100


def test_items_have_only_allowed_fields_and_survey_is_labelled_synthetic(world):
    mixed = world.s["mixed"].suggestion_id
    items = world.get(f"/api/suggestions/{mixed}/evidence?page_size=200").json()["items"]
    reviews = [i for i in items if i["kind"] == "review"]
    surveys = [i for i in items if i["kind"] == "survey"]
    assert [i["kind"] for i in items] == ["review"] * 120 + ["survey"] * 7  # 종류 순, 그 안에서 evidence_id 오름차순
    assert set(reviews[0]) == {"kind", "evidence_id", "rating", "date"}
    assert set(surveys[0]) == {"kind", "evidence_id", "synthetic_label"} and all(s["synthetic_label"] == "합성" for s in surveys)
    text = json.dumps(items, ensure_ascii=False)
    for forbidden in ("author", "variant", "title", "review_text", SECRET, "변형값"):
        assert forbidden not in text


def test_kind_filter(world):
    mixed = world.s["mixed"].suggestion_id
    only_survey = world.get(f"/api/suggestions/{mixed}/evidence?kind=survey").json()
    assert only_survey["total"] == 7 and {i["kind"] for i in only_survey["items"]} == {"survey"}
    only_review = world.get(f"/api/suggestions/{mixed}/evidence?kind=review").json()
    assert only_review["total"] == 120


def test_empty_union_and_errors(world):
    empty = world.get(f"/api/suggestions/{world.s['empty'].suggestion_id}/evidence").json()
    assert empty == {"total": 0, "page": 1, "page_size": 50, "items": []}
    sid = world.s["mixed"].suggestion_id
    assert world.get("/api/suggestions/9999/evidence").json()["error"]["code"] == "NOT_FOUND"
    for bad in ("page=0", "page_size=0", "page_size=201", "kind=other", "page=abc"):
        response = world.get(f"/api/suggestions/{sid}/evidence?{bad}")
        assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR", bad
    assert world.get("/api/suggestions/abc/evidence").status_code == 422


def test_unknown_row_ids_are_ignored():
    snapshot_ids = {"a": {"kind": "review", "ids": [3, 1]}}
    assert evidence_by_kind(snapshot_ids, ["a", "missing"]) == {"review": [1, 3], "survey": []}


def test_survey_evidence_viewer(world):
    response_id = world.response_ids[0]
    response = world.get(f"/api/evidence/survey/{response_id}")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"kind", "response_id", "synthetic_label", "round", "answers"}
    assert body["kind"] == "survey" and body["synthetic_label"] == "합성" and body["round"]["label"] == "2026-Q1"
    assert len(body["answers"]) >= 10 and set(body["answers"][0]) == {"question_text", "value"}
    # 값은 코드가 아니라 선택지 라벨이다 (예: 5점 척도의 '매우 만족'), 문항 순서대로이다
    assert not any(a["value"] in {"1", "2", "3", "4", "5"} for a in body["answers"])
    assert body["answers"][0]["question_text"].startswith("카메라를 사용해 본")
    assert world.get("/api/evidence/survey/99999").json()["error"]["code"] == "NOT_FOUND"
    assert world.get("/api/evidence/survey/abc").status_code == 422
