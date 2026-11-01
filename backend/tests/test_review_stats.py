"""A-11(포트폴리오 데모) 집계 테스트. SQLite만 쓰고 Supabase와 OpenAI에는 접속하지 않는다.

시험 데이터는 모두 만들어 낸 값이다. 실제 리뷰는 쓰지 않는다.
"""

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import get_session
from app.main import app
from app.models import Product, Review
from app.services.review_stats import ReviewRow, aggregate_review_stats, has_text, load_review_rows

SECRET_TEXT = "시험용-본문-표식-응답에-있으면-안-됨"
SECRET_TITLE = "시험용-제목-표식-응답에-있으면-안-됨"
SECRET_VARIANT = "시험용-옵션-표식-응답에-있으면-안-됨"
FORBIDDEN_KEYS = {"title", "review_text", "author", "variant", "review_id"}


def row(product="상품A", rating=5, day=datetime.date(2026, 1, 15), has_text=True):
    return ReviewRow(product, rating, day, has_text)


# ---- 집계 함수 (8) ----


def test_rating_distribution_is_counted_per_product():
    stats = aggregate_review_stats(
        [row("상품A", 5), row("상품A", 5), row("상품A", 1), row("상품B", 3)]
    )
    by_name = {p["product_name"]: p for p in stats["products"]}
    assert {c["rating"]: c["count"] for c in by_name["상품A"]["rating_distribution"]} == {1: 1, 2: 0, 3: 0, 4: 0, 5: 2}
    assert {c["rating"]: c["count"] for c in by_name["상품B"]["rating_distribution"]} == {1: 0, 2: 0, 3: 1, 4: 0, 5: 0}


def test_distribution_always_has_five_cells_filled_with_zero():
    stats = aggregate_review_stats([row(rating=4)])
    distribution = stats["products"][0]["rating_distribution"]
    assert [cell["rating"] for cell in distribution] == [1, 2, 3, 4, 5]
    assert [cell["count"] for cell in distribution] == [0, 0, 0, 1, 0]


def test_review_counts_and_total_match():
    stats = aggregate_review_stats([row("상품A"), row("상품A"), row("상품B")])
    assert [(p["product_name"], p["review_count"]) for p in stats["products"]] == [("상품A", 2), ("상품B", 1)]
    assert stats["total"]["review_count"] == 3
    assert sum(p["review_count"] for p in stats["products"]) == stats["total"]["review_count"]
    assert sum(cell["count"] for p in stats["products"] for cell in p["rating_distribution"]) == 3


def test_with_text_count_and_ratio():
    stats = aggregate_review_stats(
        [row("상품A", has_text=True), row("상품A", has_text=False), row("상품A", has_text=False), row("상품A", has_text=False),
         row("상품B", has_text=True)]
    )
    by_name = {p["product_name"]: p for p in stats["products"]}
    assert (by_name["상품A"]["with_text_count"], by_name["상품A"]["with_text_ratio"]) == (1, 0.25)
    assert (by_name["상품B"]["with_text_count"], by_name["상품B"]["with_text_ratio"]) == (1, 1.0)
    assert stats["total"] == {"review_count": 5, "with_text_count": 2, "with_text_ratio": 0.4}


def test_quarter_boundaries_use_calendar_quarters():
    days = [
        datetime.date(2025, 3, 31), datetime.date(2025, 4, 1), datetime.date(2025, 6, 30), datetime.date(2025, 7, 1),
        datetime.date(2025, 12, 31), datetime.date(2026, 1, 1),
    ]
    stats = aggregate_review_stats([row(day=d) for d in days])
    assert {q["quarter"]: q["count"] for q in stats["quarters"]} == {
        "2025-Q1": 1, "2025-Q2": 2, "2025-Q3": 1, "2025-Q4": 1, "2026-Q1": 1,
    }


def test_quarters_are_ascending_filled_with_zero_and_sum_to_total():
    stats = aggregate_review_stats(
        [row(day=datetime.date(2024, 11, 5)), row(day=datetime.date(2025, 9, 20)), row(day=datetime.date(2025, 9, 21))]
    )
    assert [q["quarter"] for q in stats["quarters"]] == ["2024-Q4", "2025-Q1", "2025-Q2", "2025-Q3"]
    assert [q["count"] for q in stats["quarters"]] == [1, 0, 0, 2]
    assert sum(q["count"] for q in stats["quarters"]) == stats["total"]["review_count"]


def test_empty_data_gives_zeros_and_null_ratio_without_error():
    stats = aggregate_review_stats([])
    assert stats == {
        "products": [],
        "quarters": [],
        "total": {"review_count": 0, "with_text_count": 0, "with_text_ratio": None},
    }


@pytest.mark.parametrize("bad_rating", [0, 6, -1])
def test_rating_outside_one_to_five_is_rejected(bad_rating):
    with pytest.raises(ValueError):
        aggregate_review_stats([row(rating=bad_rating)])


# ---- "본문 있음" 판정, D5 (파이썬 strip 기준) ----


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param("   ", False, id="흔한 공백만 -> 없음"),
        pytest.param("　　", False, id="전각 공백만 -> 없음"),
        pytest.param("\n\r\n", False, id="줄바꿈만 -> 없음"),
        pytest.param(" ㄱ ", True, id="공백이 아닌 글자 한 개 -> 있음"),
        pytest.param(None, False, id="NULL -> 없음"),
        pytest.param("", False, id="빈 문자열 -> 없음"),
    ],
)
def test_has_text_judgement_follows_python_strip(value, expected):
    assert has_text(value) is expected


def test_loaded_rows_do_not_keep_the_review_text(session):
    session.add(Product(product_name="상품A"))
    session.flush()
    session.add(
        Review(review_id=1, product_name="상품A", rating=5, date=datetime.date(2025, 1, 1), helpful_count=0,
               title=SECRET_TITLE, review_text=SECRET_TEXT)
    )
    session.commit()
    rows = load_review_rows(session)
    assert [r.has_text for r in rows] == [True]
    # 본문 값은 판정 후 버려진다: 행 객체에 본문을 담는 자리가 없고, 문자열 표현에도 없다.
    assert set(ReviewRow.__dataclass_fields__) == {"product_name", "rating", "date", "has_text"}
    assert SECRET_TEXT not in repr(rows) and SECRET_TITLE not in repr(rows)


# ---- API (4) ----


@pytest.fixture
def client_with_data(session_factory, session):
    for name in ("상품A", "상품B"):
        session.add(Product(product_name=name))
    session.flush()
    texts = [
        # (review_id, product, rating, date, review_text)
        (1, "상품A", 5, datetime.date(2025, 2, 1), SECRET_TEXT),  # 본문 있음
        (2, "상품A", 5, datetime.date(2025, 2, 2), None),  # NULL
        (3, "상품A", 4, datetime.date(2025, 8, 3), ""),  # 빈 문자열
        (4, "상품A", 1, datetime.date(2025, 8, 4), "   "),  # 공백만
        (5, "상품B", 3, datetime.date(2025, 8, 5), "\t\n\r"),  # 탭·줄바꿈만
        (6, "상품B", 2, datetime.date(2025, 8, 6), "　 "),  # 전각·줄바꿈 없는 공백만
        (7, "상품B", 5, datetime.date(2025, 8, 7), "  " + SECRET_TEXT + "  "),  # 앞뒤 공백 + 본문
    ]
    for review_id, product, rating, day, text in texts:
        session.add(
            Review(
                review_id=review_id, product_name=product, rating=rating, date=day, variant=SECRET_VARIANT,
                helpful_count=0, title=SECRET_TITLE, review_text=text,
            )
        )
    session.commit()

    def override_session():
        with session_factory() as db_session:
            yield db_session

    app.dependency_overrides[get_session] = override_session
    yield TestClient(app), session
    app.dependency_overrides.clear()


def collect_keys(value):
    keys = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            keys.add(key)
            keys |= collect_keys(inner)
    elif isinstance(value, list):
        for inner in value:
            keys |= collect_keys(inner)
    return keys


def test_api_returns_db_aggregates_with_text_definition(client_with_data):
    api, _ = client_with_data
    response = api.get("/api/demo/review-stats")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"products", "quarters", "total"}
    by_name = {p["product_name"]: p for p in body["products"]}
    # 본문 있음: 1번(상품A), 7번(상품B). NULL·빈 문자열·공백만·탭 줄바꿈만·전각 공백만은 제외.
    assert by_name["상품A"]["review_count"] == 4 and by_name["상품A"]["with_text_count"] == 1
    assert by_name["상품B"]["review_count"] == 3 and by_name["상품B"]["with_text_count"] == 1
    assert body["total"] == {"review_count": 7, "with_text_count": 2, "with_text_ratio": round(2 / 7, 4)}
    assert [q["quarter"] for q in body["quarters"]] == ["2025-Q1", "2025-Q2", "2025-Q3"]
    assert [q["count"] for q in body["quarters"]] == [2, 0, 5]
    # 집계로 넘어가는 행에는 "본문 있음" 참/거짓만 있고 본문 값은 없다.
    assert all(isinstance(r.has_text, bool) for r in load_review_rows(client_with_data[1]))


def test_api_response_keys_have_no_title_text_or_author(client_with_data):
    api, _ = client_with_data
    keys = collect_keys(api.get("/api/demo/review-stats").json())
    assert not (keys & FORBIDDEN_KEYS)


def test_api_response_never_contains_review_values(client_with_data):
    api, _ = client_with_data
    text = api.get("/api/demo/review-stats").text
    for marker in (SECRET_TEXT, SECRET_TITLE, SECRET_VARIANT):
        assert marker not in text


def test_api_is_read_only(client_with_data):
    api, session = client_with_data
    before = session.scalar(select(func.count()).select_from(Review))
    api.get("/api/demo/review-stats")
    api.get("/api/demo/review-stats")
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Review)) == before == 7
