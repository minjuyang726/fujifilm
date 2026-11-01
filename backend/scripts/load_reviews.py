"""쿠팡 리뷰 CSV를 product, review 테이블에 적재한다.

backend 폴더에서 실행한다.
  python scripts/load_reviews.py --check-only   # CSV만 읽어 집계를 보여 준다(DB에 쓰지 않음)
  python scripts/load_reviews.py                # DATABASE_URL이 가리키는 DB에 적재한다

- 기본 CSV 경로: database/data/coupang_fujifilm_reviews_merged.csv
- author, seller, source_file, original_no 열은 적재하지 않는다.
- 빈 문자열은 NULL로 바꾼다. 같은 CSV를 다시 적재해도 행이 늘지 않는다(같은 review_id는 갱신).
- 출력에는 건수 같은 집계만 있고 리뷰 본문과 접속 정보는 없다.
"""

import argparse
import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.dialects import postgresql, sqlite  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.models import Product, Review  # noqa: E402

COLUMNS = (
    "review_id",
    "product_name",
    "rating",
    "date",
    "variant",
    "helpful_count",
    "title",
    "review_text",
)
DEFAULT_CSV = BACKEND_DIR.parent / "database" / "data" / "coupang_fujifilm_reviews_merged.csv"
BATCH_SIZE = 500


def _null_if_blank(value):
    if value is None or value.strip() == "":
        return None
    return value


def parse_row(raw: dict, line_no: int) -> dict:
    """CSV 한 줄에서 적재할 열만 꺼낸다. 오류 메시지에는 줄 번호와 열 이름만 쓴다."""
    try:
        review_id = int(raw["review_id"])
    except (TypeError, ValueError):
        raise ValueError(f"{line_no}행: review_id가 정수가 아닙니다") from None
    try:
        rating = int(raw["rating"])
    except (TypeError, ValueError):
        raise ValueError(f"{line_no}행: rating이 정수가 아닙니다") from None
    if not 1 <= rating <= 5:
        raise ValueError(f"{line_no}행: rating이 1~5 범위가 아닙니다")
    try:
        review_date = date.fromisoformat(raw["date"])
    except (TypeError, ValueError):
        raise ValueError(f"{line_no}행: date가 YYYY-MM-DD 형식이 아닙니다") from None
    try:
        helpful_count = int(raw["helpful_count"] or 0)
    except ValueError:
        raise ValueError(f"{line_no}행: helpful_count가 정수가 아닙니다") from None
    if helpful_count < 0:
        raise ValueError(f"{line_no}행: helpful_count가 음수입니다")
    product_name = _null_if_blank(raw["product_name"])
    if product_name is None:
        raise ValueError(f"{line_no}행: product_name이 비어 있습니다")
    return {
        "review_id": review_id,
        "product_name": product_name,
        "rating": rating,
        "date": review_date,
        "variant": _null_if_blank(raw["variant"]),
        "helpful_count": helpful_count,
        "title": _null_if_blank(raw["title"]),
        "review_text": _null_if_blank(raw["review_text"]),
    }


def parse_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in COLUMNS if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV에 필요한 열이 없습니다: {', '.join(missing)}")
        rows = [parse_row(raw, line_no) for line_no, raw in enumerate(reader, start=2)]
    ids = Counter(row["review_id"] for row in rows)
    duplicated = [review_id for review_id, count in ids.items() if count > 1]
    if duplicated:
        raise ValueError(f"CSV 안에 중복된 review_id가 {len(duplicated)}개 있습니다")
    return rows


def upsert(engine, rows: list[dict]) -> None:
    """product와 review를 한 트랜잭션으로 적재한다. 같은 review_id는 갱신한다."""
    dialect = engine.dialect.name
    if dialect == "postgresql":
        insert = postgresql.insert
    elif dialect == "sqlite":
        insert = sqlite.insert
    else:
        raise RuntimeError(f"지원하지 않는 DB입니다: {dialect}")

    with engine.begin() as conn:
        product_names = sorted({row["product_name"] for row in rows})
        conn.execute(
            insert(Product).values([{"product_name": name} for name in product_names]).on_conflict_do_nothing()
        )
        for start in range(0, len(rows), BATCH_SIZE):
            statement = insert(Review).values(rows[start : start + BATCH_SIZE])
            statement = statement.on_conflict_do_update(
                index_elements=["review_id"],
                set_={name: statement.excluded[name] for name in COLUMNS if name != "review_id"},
            )
            conn.execute(statement)


def summarize_rows(rows: list[dict]) -> dict:
    """메모리의 행에서 집계를 낸다(DB에 쓰지 않는 --check-only용)."""
    ids = [row["review_id"] for row in rows]
    return {
        "product": len({row["product_name"] for row in rows}),
        "review": len(rows),
        "title_null": sum(row["title"] is None for row in rows),
        "review_text_null": sum(row["review_text"] is None for row in rows),
        "variant_not_null": sum(row["variant"] is not None for row in rows),
        "rating": dict(sorted(Counter(row["rating"] for row in rows).items(), reverse=True)),
        "review_id_min": min(ids) if ids else None,
        "review_id_max": max(ids) if ids else None,
    }


def summarize_db(engine) -> dict:
    """DB에 들어 있는 값에서 같은 집계를 낸다. 적재 결과를 확인하는 용도다."""
    with engine.connect() as conn:
        rating_rows = conn.execute(
            select(Review.rating, func.count()).group_by(Review.rating).order_by(Review.rating.desc())
        ).all()
        return {
            "product": conn.scalar(select(func.count()).select_from(Product)),
            "review": conn.scalar(select(func.count()).select_from(Review)),
            "title_null": conn.scalar(select(func.count()).select_from(Review).where(Review.title.is_(None))),
            "review_text_null": conn.scalar(
                select(func.count()).select_from(Review).where(Review.review_text.is_(None))
            ),
            "variant_not_null": conn.scalar(
                select(func.count()).select_from(Review).where(Review.variant.is_not(None))
            ),
            "rating": {rating: count for rating, count in rating_rows},
            "review_id_min": conn.scalar(select(func.min(Review.review_id))),
            "review_id_max": conn.scalar(select(func.max(Review.review_id))),
        }


def print_summary(title: str, summary: dict) -> None:
    print(f"== {title}")
    print(f"product {summary['product']}개, review {summary['review']}개")
    print(f"title이 NULL: {summary['title_null']}, review_text가 NULL: {summary['review_text_null']}")
    print(f"variant에 값이 있음: {summary['variant_not_null']}")
    print("평점별 건수: " + ", ".join(f"{rating}점 {count}" for rating, count in summary["rating"].items()))
    print(f"review_id 최솟값 {summary['review_id_min']}, 최댓값 {summary['review_id_max']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="쿠팡 리뷰 CSV를 적재한다.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="CSV 경로")
    parser.add_argument("--check-only", action="store_true", help="CSV만 읽고 DB에는 쓰지 않는다")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"실패: CSV를 찾을 수 없습니다. database/data/에 복사해 두었는지 확인해 주세요.")
        return 1
    try:
        rows = parse_rows(args.csv)
    except ValueError as error:
        print(f"실패: {error}")
        return 1
    print_summary("CSV에서 읽은 값", summarize_rows(rows))
    if args.check_only:
        return 0

    try:
        engine = make_engine()
    except RuntimeError as error:
        print(f"실패: {error}")
        return 1
    print(f"== 대상 DB: {engine.dialect.name}")
    try:
        upsert(engine, rows)
        summary = summarize_db(engine)
    except Exception as error:  # 오류 메시지에 접속 정보가 들어갈 수 있어 종류만 출력한다.
        print(f"실패: 적재하지 못했습니다 ({type(error).__name__}). 테이블이 있는지(alembic upgrade head) 확인해 주세요.")
        return 1
    print_summary("DB에 들어 있는 값", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
