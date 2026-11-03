"""집계 검증용 API(plan.md 부록 A, spec.md A-11)의 리뷰 집계.

- 집계는 코드가 한다(FR-0.1). LLM이나 OpenAI 호출은 없다.
- DB에서는 product_name, rating, date, review_text를 읽는다. review_text는 "본문 있음" 판정에만 쓰고
  판정한 뒤 바로 버린다. 응답, 로그, 예외 메시지에 넣지 않는다. title은 읽지 않는다.
- 파이썬으로 센다. 분기 계산과 공백 판정을 SQL로 하면 SQLite와 PostgreSQL의 문법이 달라 테스트와 운영이 다른 코드를 탄다.
"""

import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Review

logger = logging.getLogger(__name__)

RATINGS = (1, 2, 3, 4, 5)
RATIO_DIGITS = 4


@dataclass(frozen=True)
class ReviewRow:
    product_name: str
    rating: int
    date: date
    has_text: bool


def has_text(value: str | None) -> bool:
    """D5: 본문이 NULL이 아니고 공백을 제거했을 때 비어 있지 않으면 참. 공백 범위는 파이썬 strip()을 따른다.

    본문 값은 이 함수 안에서 판정에만 쓰고 돌려주지 않는다.
    """
    return value is not None and value.strip() != ""


def load_review_rows(session: Session) -> list[ReviewRow]:
    """집계에 필요한 열만 읽는다. SELECT만 쓴다(읽기 전용).

    review_text는 판정 직후 버리고 ReviewRow에는 담지 않는다. title과 작성자는 읽지 않는다.
    """
    statement = select(Review.product_name, Review.rating, Review.date, Review.review_text)
    rows: list[ReviewRow] = []
    for record in session.execute(statement):
        rows.append(ReviewRow(record.product_name, record.rating, record.date, has_text(record.review_text)))
    return rows


def _ratio(part: int, whole: int) -> float | None:
    return None if whole == 0 else round(part / whole, RATIO_DIGITS)


def _quarter_key(day: date) -> tuple[int, int]:
    return (day.year, (day.month - 1) // 3 + 1)


def _next_quarter(key: tuple[int, int]) -> tuple[int, int]:
    year, quarter = key
    return (year, quarter + 1) if quarter < 4 else (year + 1, 1)


def _quarter_label(key: tuple[int, int]) -> str:
    return f"{key[0]}-Q{key[1]}"


def aggregate_review_stats(rows: Iterable[ReviewRow]) -> dict:
    """상품별 평점 분포·리뷰 수·본문 비율, 달력 분기별 건수, 전체 합계를 센다.

    분기 목록은 데이터의 첫 분기부터 마지막 분기까지 빈 분기를 0건으로 채운다.
    rating이 1~5가 아니면 ValueError를 낸다(DB의 CHECK 제약과 같은 범위).
    """
    per_product: dict[str, dict] = {}
    quarter_counts: Counter = Counter()
    total_reviews = 0
    total_with_text = 0

    for row in rows:
        if row.rating not in RATINGS:
            raise ValueError("rating은 1~5여야 합니다.")
        stats = per_product.setdefault(row.product_name, {"count": 0, "text": 0, "ratings": Counter()})
        stats["count"] += 1
        stats["ratings"][row.rating] += 1
        if row.has_text:
            stats["text"] += 1
            total_with_text += 1
        quarter_counts[_quarter_key(row.date)] += 1
        total_reviews += 1

    products = [
        {
            "product_name": name,
            "review_count": stats["count"],
            "rating_distribution": [{"rating": rating, "count": stats["ratings"][rating]} for rating in RATINGS],
            "with_text_count": stats["text"],
            "with_text_ratio": _ratio(stats["text"], stats["count"]),
        }
        for name, stats in sorted(per_product.items())
    ]

    quarters: list[dict] = []
    if quarter_counts:
        key, last = min(quarter_counts), max(quarter_counts)
        while key <= last:
            quarters.append({"quarter": _quarter_label(key), "count": quarter_counts.get(key, 0)})
            key = _next_quarter(key)

    return {
        "products": products,
        "quarters": quarters,
        "total": {
            "review_count": total_reviews,
            "with_text_count": total_with_text,
            "with_text_ratio": _ratio(total_with_text, total_reviews),
        },
    }


def get_review_stats(session: Session) -> dict:
    stats = aggregate_review_stats(load_review_rows(session))
    # 로그에는 건수만 남긴다. 리뷰 값은 남기지 않는다(spec.md 7.4).
    logger.info(
        "review-stats 집계 products=%d quarters=%d total=%d",
        len(stats["products"]),
        len(stats["quarters"]),
        stats["total"]["review_count"],
    )
    return stats
