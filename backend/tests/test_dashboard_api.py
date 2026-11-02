"""A-3 설문 부분. 임시 SQLite만 쓴다. 합성 데이터를 적재 서비스로 넣어서 쓴다."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models import ProductFamily, Round, SurveyResponse
from app.services.survey_load import load_synthetic_survey
from app.services.synthetic_survey import generate


@pytest.fixture
def api(session):
    session.add_all([ProductFamily(name="일회용 카메라"), ProductFamily(name="인스탁스 즉석카메라")])
    session.add(Round(label="[파일럿-임시] 2026-11-02"))
    session.commit()
    data = generate()
    load_synthetic_survey(session, data)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    client.data = data
    yield client
    app.dependency_overrides.clear()


def round_id(session, label):
    return session.scalar(select(Round.round_id).where(Round.label == label))


def file_counts(data, label):
    from collections import Counter

    rd = next(r for r in data["rounds"] if r["label"] == label)
    return {q["code"]: Counter(v for a in rd["responses"] for v in a[q["code"]]) for q in rd["questions"]}


def test_dashboard_returns_family_round_and_survey_only(api, session):
    rid = round_id(session, "2026-Q1")
    response = api.get(f"/api/families/1/dashboard?round_id={rid}")
    assert response.status_code == 200 and response.headers["x-request-id"]
    body = response.json()
    assert set(body) == {"family", "round", "survey"}  # voc는 Phase 4
    assert body["family"] == {"family_id": 1, "name": "일회용 카메라"}
    assert body["round"] == {"round_id": rid, "label": "2026-Q1"}
    survey = body["survey"]
    assert set(survey) == {"respondent_count", "synthetic_label", "scope", "questions"}
    assert survey["respondent_count"] == 100 and survey["scope"] == "common" and survey["synthetic_label"] == "합성"
    assert [q["question_id"] for q in survey["questions"]] == sorted(q["question_id"] for q in survey["questions"])
    assert len(survey["questions"]) == 10
    assert set(survey["questions"][0]) == {"question_id", "text", "type", "results"}
    assert set(survey["questions"][0]["results"][0]) == {"code", "option", "count", "ratio"}


def test_counts_match_the_generated_data_for_both_rounds(api, session):
    for label in ("2026-Q1", "2026-Q2"):
        survey = api.get(f"/api/families/1/dashboard?round_id={round_id(session, label)}").json()["survey"]
        expected = file_counts(api.data, label)
        for question in survey["questions"]:
            code = next(q for q in api.data["rounds"][0]["questions"] if q["text"] == question["text"])["code"]
            got = {r["code"]: r["count"] for r in question["results"]}
            assert got == {c: expected[code].get(c, 0) for c in got}, (label, code)
            labels = [r["option"] for r in question["results"]]
            assert all(labels)


def test_rounds_differ_where_the_probability_tables_differ(api, session):
    q1 = api.get(f"/api/families/1/dashboard?round_id={round_id(session, '2026-Q1')}").json()["survey"]
    q2 = api.get(f"/api/families/1/dashboard?round_id={round_id(session, '2026-Q2')}").json()["survey"]
    assert q1["questions"] != q2["questions"]


def test_family_does_not_change_the_survey(api, session):
    rid = round_id(session, "2026-Q1")
    first = api.get(f"/api/families/1/dashboard?round_id={rid}").json()
    second = api.get(f"/api/families/2/dashboard?round_id={rid}").json()
    assert first["family"] != second["family"]
    assert first["survey"] == second["survey"] and first["round"] == second["round"]


def test_ratio_is_count_over_respondents_rounded_to_four_digits_and_multi_can_exceed_one(api, session):
    survey = api.get(f"/api/families/1/dashboard?round_id={round_id(session, '2026-Q1')}").json()["survey"]
    n = survey["respondent_count"]
    for question in survey["questions"]:
        for result in question["results"]:
            assert result["ratio"] == round(result["count"] / n, 4)
        total = sum(r["ratio"] for r in question["results"])
        if question["type"] == "multi":
            assert total > 1.0  # 복수응답: 합이 100%를 넘는다
            assert sum(r["count"] for r in question["results"]) > n
        else:
            assert total == pytest.approx(1.0, abs=0.0005)
            assert sum(r["count"] for r in question["results"]) == n


def test_zero_count_options_are_included_in_option_order(api, session):
    survey = api.get(f"/api/families/1/dashboard?round_id={round_id(session, '2026-Q1')}").json()["survey"]
    for question in survey["questions"]:
        codes = [r["code"] for r in question["results"]]
        assert codes == [str(i) for i in range(1, len(codes) + 1)]


def test_synthetic_label_is_null_when_a_non_synthetic_response_is_mixed_in(api, session):
    rid = round_id(session, "2026-Q1")
    session.add(SurveyResponse(round_id=rid, family_id=None, is_synthetic=False))
    session.commit()
    survey = api.get(f"/api/families/1/dashboard?round_id={rid}").json()["survey"]
    assert survey["synthetic_label"] is None and survey["respondent_count"] == 101


def test_round_without_responses_gives_zero_counts_and_no_label(api, session):
    session.add(Round(label="2026-Q3"))
    session.commit()
    survey = api.get(f"/api/families/1/dashboard?round_id={round_id(session, '2026-Q3')}").json()["survey"]
    assert survey["respondent_count"] == 0 and survey["synthetic_label"] is None and survey["questions"] == []


def error_of(response, status, code):
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code and error["request_id"] == response.headers["x-request-id"]
    return error


def test_not_found_cases(api, session):
    rid = round_id(session, "2026-Q1")
    error_of(api.get(f"/api/families/999/dashboard?round_id={rid}"), 404, "NOT_FOUND")
    error_of(api.get("/api/families/1/dashboard?round_id=999"), 404, "NOT_FOUND")
    pilot = session.scalar(select(Round.round_id).where(Round.label.like("[파일럿-임시]%")))
    error_of(api.get(f"/api/families/1/dashboard?round_id={pilot}"), 404, "NOT_FOUND")


def test_validation_errors(api):
    error = error_of(api.get("/api/families/1/dashboard"), 422, "VALIDATION_ERROR")
    assert error["details"][0]["field"].endswith("round_id")
    error_of(api.get("/api/families/1/dashboard?round_id=abc"), 422, "VALIDATION_ERROR")
    error_of(api.get("/api/families/abc/dashboard?round_id=1"), 422, "VALIDATION_ERROR")
