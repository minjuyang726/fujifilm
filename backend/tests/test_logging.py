"""JSON 로그(spec.md 7.3, 7.4). 로그에 본문, 쿼리 문자열, 예외 메시지, 키가 남지 않는다."""

import json
import logging
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter, setup_logging
from app.db import get_session
from app.main import app
from app.models import Product, Review

BODY = "가짜본문-로그에-남으면-안-됨"
QUERY_VALUE = "쿼리값-로그에-남으면-안-됨"
FAKE_KEY = "sk-fake-key-for-test-0000"
FAKE_URL = "postgresql://user:fakepass@host/db"


@pytest.fixture
def log_file(tmp_path):
    path = setup_logging(tmp_path / "logs")
    yield path
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_fujifilm_json", False):
            root.removeHandler(handler)
            handler.close()
    setup_logging()  # 다른 테스트를 위해 기본 위치로 되돌린다


def read_lines(path):
    for handler in logging.getLogger().handlers:
        handler.flush()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_request_is_logged_as_one_json_line_with_common_fields(log_file, session):
    session.add(Product(product_name="p"))
    session.flush()
    session.add(Review(review_id=1, product_name="p", rating=5, date=date(2026, 2, 1), helpful_count=0, title="t", review_text=BODY))
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    try:
        response = TestClient(app).get(f"/api/evidence/review/1?x={QUERY_VALUE}")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200 and BODY in response.text
    lines = [line for line in read_lines(log_file) if line["event"] == "request"]
    assert len(lines) == 1
    line = lines[0]
    assert {"timestamp", "level", "request_id", "event", "duration_ms"} <= set(line)
    assert line["request_id"] == response.headers["x-request-id"]
    assert (line["method"], line["path"], line["status"], line["level"]) == ("GET", "/api/evidence/review/1", 200, "INFO")
    text = log_file.read_text(encoding="utf-8")
    assert BODY not in text and QUERY_VALUE not in text


def test_unexpected_error_logs_type_and_location_but_not_the_message(log_file):
    def broken():
        raise RuntimeError(f"{FAKE_URL} {FAKE_KEY} {BODY}")

    app.dependency_overrides[get_session] = broken
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/api/families")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500
    lines = read_lines(log_file)
    errors = [line for line in lines if line["event"] == "unhandled_error"]
    assert len(errors) == 1
    assert errors[0]["level"] == "ERROR" and errors[0]["error_type"] == "RuntimeError"
    assert errors[0]["request_id"] == response.headers["x-request-id"] and errors[0]["location"]
    text = log_file.read_text(encoding="utf-8")
    for forbidden in (FAKE_URL, FAKE_KEY, BODY, "fakepass"):
        assert forbidden not in text
    request_line = [line for line in lines if line["event"] == "request"][0]
    assert request_line["status"] == 500


def test_setup_logging_is_idempotent_and_creates_the_directory(tmp_path):
    root = logging.getLogger()
    before = len(root.handlers)
    first = setup_logging(tmp_path / "a")
    second = setup_logging(tmp_path / "a")
    assert first == second and first.parent.is_dir()
    assert len(root.handlers) == before + 2 or len(root.handlers) >= 2
    marked = [h for h in root.handlers if getattr(h, "_fujifilm_json", False)]
    assert len(marked) == 2  # 표준 출력 + 파일
    for handler in marked:
        root.removeHandler(handler)
        handler.close()
    setup_logging()


def test_formatter_keeps_older_string_logs_as_json():
    record = logging.LogRecord("x", logging.WARNING, __file__, 1, "광고성 판정 재시도 code=%s", ("TIMEOUT",), None)
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["level"] == "WARNING" and parsed["event"] == "광고성 판정 재시도 code=TIMEOUT"
