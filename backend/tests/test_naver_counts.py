"""네이버 검색 건수 수집(제한 구현 A안). 네트워크에 접속하지 않고 모든 값은 가짜다."""

import io
import json
import urllib.error

import pytest
from sqlalchemy import select

from app.models import NaverSearchCount
from app.services.naver_counts import MAX_QUERIES, NaverError, collect_counts, make_fetch, save_counts


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_returning(payload, calls):
    def opener(request, timeout):
        calls.append({"url": request.full_url, "headers": dict(request.header_items()), "timeout": timeout})
        return FakeResponse(json.dumps(payload).encode())

    return opener


FULL_PAYLOAD = {
    "lastBuildDate": "x", "total": 1234, "start": 1, "display": 1,
    "items": [{"title": "제목 가나다", "link": "http://example.invalid/a", "description": "요약 가나다", "bloggername": "이름"}],
}


def test_fetch_sends_the_documented_request_and_returns_only_total():
    calls = []
    fetch = make_fetch("id-value", "secret-value", opener=opener_returning(FULL_PAYLOAD, calls))
    assert fetch("blog", "시험 질의") == 1234
    call = calls[0]
    assert call["url"].startswith("https://naverapihub.apigw.ntruss.com/search/v1/blog?")
    assert "display=1" in call["url"] and "start=1" in call["url"] and "sort=sim" in call["url"]
    assert call["timeout"] == 10
    assert call["headers"]["X-ncp-apigw-api-key-id"] == "id-value" and call["headers"]["X-ncp-apigw-api-key"] == "secret-value"
    assert make_fetch("a", "b", opener=opener_returning(FULL_PAYLOAD, []))("cafearticle", "q") == 1234


@pytest.mark.parametrize("payload", [{}, {"total": "12"}, {"total": -1}, {"total": True}, {"total": 1.5}])
def test_bad_total_is_rejected(payload):
    with pytest.raises(NaverError) as error:
        make_fetch("a", "b", opener=opener_returning(payload, []))("blog", "q")
    assert str(error.value) == "BAD_RESPONSE"


def test_http_error_and_network_error_carry_only_a_code():
    def http_error(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "secret-value in message", {}, None)

    def network_error(request, timeout):
        raise TimeoutError("secret-value")

    with pytest.raises(NaverError) as first:
        make_fetch("id-value", "secret-value", opener=http_error)("blog", "q")
    with pytest.raises(NaverError) as second:
        make_fetch("id-value", "secret-value", opener=network_error)("blog", "q")
    assert str(first.value) == "HTTP_429" and str(second.value) == "REQUEST_FAILED"
    assert "secret-value" not in str(first.value) + str(second.value)


def test_collect_calls_once_per_query_and_source_without_retry():
    seen = []

    def fetch(source, query):
        seen.append((source, query))
        return 7

    results = collect_counts(["가", " 나 "], fetch)
    assert seen == [("blog", "가"), ("cafearticle", "가"), ("blog", "나"), ("cafearticle", "나")]
    assert results == [("blog", "가", 7), ("cafearticle", "가", 7), ("blog", "나", 7), ("cafearticle", "나", 7)]


def test_collect_failure_stops_at_the_first_error_and_returns_nothing():
    calls = []

    def fetch(source, query):
        calls.append((source, query))
        raise NaverError("HTTP_500")

    with pytest.raises(NaverError):
        collect_counts(["가", "나"], fetch)
    assert len(calls) == 1  # 재시도하지 않고 바로 멈춘다


@pytest.mark.parametrize("queries,code", [([], "NO_QUERY"), (["  "], "NO_QUERY"), (["가", "가"], "DUPLICATE_QUERY"), ([str(i) for i in range(MAX_QUERIES + 1)], "TOO_MANY_QUERIES")])
def test_query_limits(queries, code):
    with pytest.raises(NaverError) as error:
        collect_counts(queries, lambda s, q: 1)
    assert str(error.value) == code


def test_save_stores_only_counts(session):
    saved = save_counts(session, [("blog", "가", 10), ("cafearticle", "가", 3)])
    rows = session.scalars(select(NaverSearchCount).order_by(NaverSearchCount.count_id)).all()
    assert saved == 2 and [(r.source, r.query, r.total) for r in rows] == [("blog", "가", 10), ("cafearticle", "가", 3)]
    assert {column.name for column in NaverSearchCount.__table__.columns} == {"count_id", "source", "query", "total", "collected_at"}
    assert rows[0].collected_at is not None
