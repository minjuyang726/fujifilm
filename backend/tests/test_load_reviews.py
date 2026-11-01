"""리뷰 적재 테스트. 아래 CSV 값은 모두 시험용으로 만든 가짜 값이다(실제 리뷰가 아님)."""

import csv

import pytest
from sqlalchemy import func, inspect, select

from app.db import make_engine
from app.models import Base, Product, Review
from scripts.load_reviews import parse_rows, summarize_db, upsert

HEADER = [
    "review_id", "product_name", "source_file", "original_no", "rating", "date",
    "author", "seller", "variant", "helpful_count", "title", "review_text",
]


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)


def sample_rows():
    return [
        ["1", "상품A", "a.csv", "900", "5", "2026-01-02", "가*나", "", "", "3", "제목 있음", "본문 있음"],
        ["2", "상품A", "a.csv", "901", "1", "2026-01-03", "다*라", "", "", "0", "", ""],
        ["3", "상품B", "b.csv", "902", "4", "2026-02-01", "마*바", "", "옵션1", "7", "제목만", ""],
    ]


@pytest.fixture
def engine(tmp_path):
    db = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(db)
    return db


def test_blank_values_become_null_and_counts_match(tmp_path, engine):
    csv_path = tmp_path / "reviews.csv"
    write_csv(csv_path, sample_rows())
    upsert(engine, parse_rows(csv_path))
    summary = summarize_db(engine)
    assert summary["product"] == 2
    assert summary["review"] == 3
    assert summary["title_null"] == 1
    assert summary["review_text_null"] == 2
    assert summary["variant_not_null"] == 1
    assert summary["rating"] == {5: 1, 4: 1, 1: 1}
    assert (summary["review_id_min"], summary["review_id_max"]) == (1, 3)


def test_loading_twice_does_not_add_rows(tmp_path, engine):
    csv_path = tmp_path / "reviews.csv"
    write_csv(csv_path, sample_rows())
    rows = parse_rows(csv_path)
    upsert(engine, rows)
    upsert(engine, rows)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Review)) == 3
        assert conn.scalar(select(func.count()).select_from(Product)) == 2


def test_author_and_unused_columns_are_not_in_the_table():
    columns = {column.name for column in Review.__table__.columns}
    assert columns == {
        "review_id", "product_name", "rating", "date", "variant",
        "helpful_count", "title", "review_text",
    }
    assert "author" not in columns


def test_table_created_by_models_has_no_author_column(engine):
    names = {column["name"] for column in inspect(engine).get_columns("review")}
    assert "author" not in names


@pytest.mark.parametrize(
    "bad_row",
    [
        ["1", "상품A", "a.csv", "900", "6", "2026-01-02", "가*나", "", "", "0", "", ""],
        ["1", "상품A", "a.csv", "900", "5", "2026/01/02", "가*나", "", "", "0", "", ""],
        ["x", "상품A", "a.csv", "900", "5", "2026-01-02", "가*나", "", "", "0", "", ""],
    ],
)
def test_invalid_rows_are_rejected(tmp_path, bad_row):
    csv_path = tmp_path / "bad.csv"
    write_csv(csv_path, [bad_row])
    with pytest.raises(ValueError):
        parse_rows(csv_path)


def test_duplicate_review_ids_are_rejected(tmp_path):
    csv_path = tmp_path / "dup.csv"
    rows = sample_rows()
    rows[1][0] = "1"
    write_csv(csv_path, rows)
    with pytest.raises(ValueError):
        parse_rows(csv_path)
