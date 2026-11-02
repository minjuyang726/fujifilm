"""대시보드(A-3)의 외부 VOC 집계. 계산은 코드가 한다(FR-0.1). 읽기 전용이고 리뷰 본문은 읽지 않는다.

- 대상: 선택한 제품군(product.family_id)의 리뷰 중 날짜가 회차의 period_start~period_end 안(양 끝 포함)인 것.
- 세 묶음(FR-1.11): 판정(성공한 판정이 있는 글) / 미판정(판정 대상이지만 성공한 판정이 없는 글) / 제목·본문 없음.
- 판정 읽기: 글마다 status='ok'인 판정 중 가장 최근(judged_at, 같으면 judgement_id가 큰 쪽) 1건. round_id로 거르지 않는다.
- 가중치 = max(하한, ad_weight). 저장된 ad_weight는 바꾸지 않는다(Q-7).
- 가중 건수 = 가중치의 합, 가중 평균 = Σ(가중치×평점) ÷ Σ가중치, 가중 분포 = 점수별 가중치의 합. 서버는 4자리로 반올림한다.
- 미판정과 제목·본문 없음은 가중치를 주지 않고 건수와 평점 분포만 낸다(P-5).
"""

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdJudgement, Product, Review, Round

ROUND_DIGITS = 4
RATINGS = (1, 2, 3, 4, 5)
TEMP_ROUND_PREFIX = "[파일럿-임시]"


def _rounded(value: float) -> float:
    return round(value, ROUND_DIGITS)


def _count_distribution(ratings: list[int]) -> list[dict]:
    return [{"rating": r, "count": sum(1 for x in ratings if x == r)} for r in RATINGS]


def _latest_ok_weights(session: Session, review_ids: set[int]) -> tuple[dict[int, float], set[int]]:
    """글마다 가장 최근의 성공한 판정의 가중치와, 성공한 판정이 없고 실패만 있는 글의 id."""
    latest: dict[int, tuple] = {}
    failed: set[int] = set()
    rows = session.execute(
        select(
            AdJudgement.review_id,
            AdJudgement.status,
            AdJudgement.ad_weight,
            AdJudgement.ad_probability,
            AdJudgement.judged_at,
            AdJudgement.judgement_id,
        ).order_by(AdJudgement.review_id, AdJudgement.judged_at, AdJudgement.judgement_id)
    )
    for review_id, status, ad_weight, ad_probability, judged_at, judgement_id in rows:
        if review_id not in review_ids:
            continue
        if status == "ok":
            weight = ad_weight if ad_weight is not None else 1.0 - ad_probability
            latest[review_id] = (judged_at, judgement_id, weight)  # 정렬 순서상 마지막이 가장 최근이다
        else:
            failed.add(review_id)
    return {rid: v[2] for rid, v in latest.items()}, failed - set(latest)


def voc_section(session: Session, family_id: int, round_row: Round, *, weight_floor: float, small_sample_threshold: int) -> dict:
    # 제품군의 리뷰: 본문은 읽지 않고 제목·본문 존재 여부만 읽는다.
    reviews = session.execute(
        select(
            Review.review_id,
            Review.rating,
            Review.date,
            (Review.title.is_not(None) | Review.review_text.is_not(None)).label("has_text"),
        )
        .join(Product, Product.product_name == Review.product_name)
        .where(Product.family_id == family_id)
    ).all()

    start, end = round_row.period_start, round_row.period_end

    def in_period(d: date, a: date | None, b: date | None) -> bool:
        return a is not None and b is not None and a <= d <= b

    other_periods = [
        (r.period_start, r.period_end)
        for r in session.scalars(select(Round).where(Round.round_id != round_row.round_id))
        if not r.label.startswith(TEMP_ROUND_PREFIX)
    ]

    in_round = [r for r in reviews if in_period(r.date, start, end)]
    outside = [r for r in reviews if not in_period(r.date, start, end)]
    other_round_count = sum(1 for r in outside if any(in_period(r.date, a, b) for a, b in other_periods))
    outside_rounds_count = len(outside) - other_round_count

    weights, failed_only = _latest_ok_weights(session, {r.review_id for r in in_round})

    judged = [r for r in in_round if r.has_text and r.review_id in weights]
    unjudged = [r for r in in_round if r.has_text and r.review_id not in weights]
    no_text = [r for r in in_round if not r.has_text]

    # 비가중
    judged_ratings = [r.rating for r in judged]
    unweighted = {
        "count": len(judged),
        "mean_rating": _rounded(sum(judged_ratings) / len(judged)) if judged else None,
        "rating_distribution": _count_distribution(judged_ratings),
    }
    # 가중: 가중치 = max(하한, ad_weight)
    w = {r.review_id: max(weight_floor, weights[r.review_id]) for r in judged}
    total_w = sum(w.values())
    by_rating: dict[int, float] = defaultdict(float)
    for r in judged:
        by_rating[r.rating] += w[r.review_id]
    weighted = {
        "count": _rounded(total_w),
        "mean_rating": _rounded(sum(w[r.review_id] * r.rating for r in judged) / total_w) if judged else None,
        "rating_distribution": [{"rating": rating, "count": _rounded(by_rating.get(rating, 0.0))} for rating in RATINGS],
    }

    return {
        "weight_floor": weight_floor,
        "small_sample_threshold": small_sample_threshold,
        "small_sample": len(judged) < small_sample_threshold,
        "counts": {
            "total": len(in_round),
            "judged": len(judged),
            "unjudged": len(unjudged),
            "no_text": len(no_text),
        },
        "unweighted": unweighted,
        "weighted": weighted,
        "unjudged": {
            "count": len(unjudged),
            "failed_count": sum(1 for r in unjudged if r.review_id in failed_only),
            "rating_distribution": _count_distribution([r.rating for r in unjudged]),
        },
        "no_text": {"count": len(no_text), "rating_distribution": _count_distribution([r.rating for r in no_text])},
        "excluded": {
            "count": len(outside),
            "other_round_count": other_round_count,
            "outside_rounds_count": outside_rounds_count,
        },
    }
