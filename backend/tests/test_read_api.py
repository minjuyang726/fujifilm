"""A-1, A-2, A-4와 오류 형식(spec.md 7.1). 임시 SQLite만 쓴다. 본문은 가짜 문장이다."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import Product, ProductFamily, Review, Round

SECRET_TEXT = "가짜본문-절대로-로그에-남으면-안-됨"
FAKE_TITLE = "가짜제목-본문이-없을때만-나온다"


@pytest.fixture
def api(session):
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


def add_reviews(session):
    session.add(Product(product_name="p"))
    session.flush()
    session.add_all(
        [
            Review(review_id=1, product_name="p", rating=5, date=date(2026, 2, 1), helpful_count=0, variant="변형값", title="제목A", review_text=SECRET_TEXT),
            Review(review_id=2, product_name="p", rating=3, date=date(2026, 5, 1), helpful_count=0, title=FAKE_TITLE, review_text=None),
            Review(review_id=3, product_name="p", rating=4, date=date(2026, 6, 1), helpful_count=0, title=None, review_text=None),
        ]
    )
    session.commit()


def assert_error(response, status, code):
    body = response.json()
    assert response.status_code == status
    assert set(body) == {"error"}
    error = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert error["request_id"] and response.headers["x-request-id"] == error["request_id"]
    return error


def test_families_empty_before_seed_then_listed(api, session):
    response = api.get("/api/families")
    assert response.status_code == 200 and response.json() == {"families": []}
    assert response.headers["x-request-id"]
    session.add_all([ProductFamily(name="일회용 카메라"), ProductFamily(name="인스탁스 즉석카메라")])
    session.commit()
    assert api.get("/api/families").json() == {
        "families": [{"family_id": 1, "name": "일회용 카메라"}, {"family_id": 2, "name": "인스탁스 즉석카메라"}]
    }


def test_rounds_exclude_temp_prefix_rows_and_are_ordered(api, session):
    session.add_all(
        [
            Round(label="[파일럿-임시] 2026-11-02"),
            Round(label="2026-Q1", period_start=date(2026, 1, 1), period_end=date(2026, 3, 31)),
            Round(label="2026-Q2", period_start=date(2026, 4, 1), period_end=date(2026, 6, 30)),
            Round(label="내용에 [파일럿-임시]가 있어도 접두어가 아니면 보인다"),
        ]
    )
    session.commit()
    rounds = api.get("/api/rounds").json()["rounds"]
    assert [r["label"] for r in rounds] == ["2026-Q1", "2026-Q2", "내용에 [파일럿-임시]가 있어도 접두어가 아니면 보인다"]
    assert rounds[0] == {"round_id": 2, "label": "2026-Q1", "period_start": "2026-01-01", "period_end": "2026-03-31"}
    assert rounds[2]["period_start"] is None


def test_review_evidence_has_only_the_allowed_fields(api, session):
    add_reviews(session)
    response = api.get("/api/evidence/review/1")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"kind", "review_id", "rating", "date", "review_text", "text_source"}
    assert body == {"kind": "review", "review_id": 1, "rating": 5, "date": "2026-02-01", "review_text": SECRET_TEXT, "text_source": "review_text"}
    assert "author" not in body and "variant" not in body and "title" not in body and "변형값" not in response.text


def test_title_is_used_only_when_the_body_is_missing(api, session):
    add_reviews(session)
    body = api.get("/api/evidence/review/2").json()
    assert body["review_text"] == FAKE_TITLE and body["text_source"] == "title"
    none = api.get("/api/evidence/review/3").json()
    assert none["review_text"] is None and none["text_source"] is None and none["rating"] == 4


def test_evidence_errors(api, session):
    add_reviews(session)
    assert_error(api.get("/api/evidence/review/999"), 404, "NOT_FOUND")
    error = assert_error(api.get("/api/evidence/review/abc"), 422, "VALIDATION_ERROR")
    assert error["details"][0]["field"].endswith("evidence_id")
    assert "abc" not in str(error)  # 입력 값은 오류 본문에 되돌려 주지 않는다
    assert_error(api.get("/api/evidence/other/1"), 422, "VALIDATION_ERROR")
    assert_error(api.get("/api/evidence/survey/1"), 404, "NOT_FOUND")  # 설문 근거는 Phase 5부터 조회된다(없는 번호는 404)


def test_unknown_route_and_method_use_the_same_error_shape(api):
    assert_error(api.get("/api/nothing"), 404, "NOT_FOUND")
    assert_error(api.post("/api/families"), 405, "METHOD_NOT_ALLOWED")


def test_request_ids_differ_and_incoming_header_is_not_trusted(api):
    first = api.get("/api/families", headers={"X-Request-ID": "attacker-value"})
    second = api.get("/api/families")
    assert first.headers["x-request-id"] != "attacker-value"
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_unexpected_error_becomes_500_without_internal_details(session):
    def broken():
        raise RuntimeError("postgresql://user:pass@host/db SELECT secret FROM review")

    app.dependency_overrides[get_session] = broken
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/api/families")
    finally:
        app.dependency_overrides.clear()
    error = assert_error(response, 500, "INTERNAL_ERROR")
    assert "pass" not in response.text and "SELECT" not in response.text and "details" not in error


def test_existing_pipeline_errors_follow_the_common_shape(api, session):
    response = api.get("/api/runs/12345")
    error = assert_error(response, 404, "NOT_FOUND")
    assert error["message"]
    assert_error(api.get("/api/runs/abc"), 422, "VALIDATION_ERROR")
