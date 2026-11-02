"""A-3의 voc 응답을 서비스 코드를 거치지 않은 SQL 집계와 비교한다. 읽기 전용이고 숫자만 출력한다.

backend 폴더에서 실행한다.
  python scripts/verify_voc_dashboard.py

- DATABASE_URL이 가리키는 DB를 읽기만 한다(SELECT만 쓴다). OpenAI를 부르지 않는다.
- 제품군 x 회차의 모든 조합에서 건수, 평균 평점, 평점 분포, 가중 합계를 비교하고 다른 칸이 있으면 알린다.
- 리뷰 본문과 제목은 읽지 않는다(제목·본문의 존재 여부만 SQL에서 쓴다).
"""

import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import make_engine  # noqa: E402
from app.main import app  # noqa: E402

logging.disable(logging.CRITICAL)  # 앱의 요청 로그가 출력에 섞이지 않게 한다(숫자만 출력)

TOLERANCE = 0.00006  # 서버가 4자리로 반올림한다
PREFIX = "[파일럿-임시]"

# 글마다 status='ok'인 판정 중 가장 최근 1건(judged_at, 같으면 judgement_id가 큰 쪽)
BASE = """
with latest as (
  select review_id, ad_weight from (
    select review_id, ad_weight,
           row_number() over (partition by review_id order by judged_at desc, judgement_id desc) as rn
    from ad_judgement where status = 'ok'
  ) t where rn = 1
),
cell as (
  select r.review_id, r.rating, r.date,
         (r.title is not null or r.review_text is not null) as has_text,
         l.ad_weight as w,
         (select count(*) from ad_judgement f where f.review_id = r.review_id and f.status <> 'ok') as failed_n
  from review r join product p on p.product_name = r.product_name
  left join latest l on l.review_id = r.review_id
  where p.family_id = :family
)
"""

INSIDE = "date between :s and :e"
WEIGHT = "(case when w < :floor then :floor else w end)"


def sql_numbers(conn, family, start, end, other_periods, floor):
    p = {"family": family, "s": start, "e": end, "floor": floor}
    row = conn.execute(
        text(
            BASE
            + f"""select
            sum(case when {INSIDE} and has_text and w is not null then 1 else 0 end),
            sum(case when {INSIDE} and has_text and w is null then 1 else 0 end),
            sum(case when {INSIDE} and not has_text then 1 else 0 end),
            sum(case when {INSIDE} and has_text and w is null and failed_n > 0 then 1 else 0 end),
            sum(case when not ({INSIDE}) then 1 else 0 end),
            sum(case when {INSIDE} and has_text and w is not null then {WEIGHT} else 0 end),
            sum(case when {INSIDE} and has_text and w is not null then {WEIGHT} * rating else 0 end),
            sum(case when {INSIDE} and has_text and w is not null then rating else 0 end)
          from cell"""
        ),
        p,
    ).one()
    judged, unjudged, no_text, failed, excluded, w_sum, wr_sum, r_sum = (x or 0 for x in row)
    dist = {"judged": {}, "weighted": {}, "unjudged": {}, "no_text": {}}
    for rating, nj, nw, nu, nn in conn.execute(
        text(
            BASE
            + f"""select rating,
            sum(case when {INSIDE} and has_text and w is not null then 1 else 0 end),
            sum(case when {INSIDE} and has_text and w is not null then {WEIGHT} else 0 end),
            sum(case when {INSIDE} and has_text and w is null then 1 else 0 end),
            sum(case when {INSIDE} and not has_text then 1 else 0 end)
          from cell group by rating"""
        ),
        p,
    ):
        dist["judged"][rating], dist["weighted"][rating] = int(nj or 0), float(nw or 0)
        dist["unjudged"][rating], dist["no_text"][rating] = int(nu or 0), int(nn or 0)
    other = 0
    if other_periods:
        conds = " or ".join(f"(date between :s{i} and :e{i})" for i in range(len(other_periods)))
        params = dict(p)
        for i, (a, b) in enumerate(other_periods):
            params[f"s{i}"], params[f"e{i}"] = a, b
        other = conn.execute(text(BASE + f"select count(*) from cell where not ({INSIDE}) and ({conds})"), params).scalar() or 0
    return {
        "judged": int(judged),
        "unjudged": int(unjudged),
        "no_text": int(no_text),
        "failed": int(failed),
        "excluded": int(excluded),
        "other": int(other),
        "w_sum": float(w_sum),
        "mean": (r_sum / judged) if judged else None,
        "w_mean": (wr_sum / w_sum) if judged else None,
        "dist": dist,
    }


def close(a, b):
    if a is None or b is None:
        return a is b
    return abs(a - b) <= TOLERANCE


def cell_of(distribution, rating):
    return next(c["count"] for c in distribution if c["rating"] == rating)


def main() -> int:
    floor = get_settings().ad_weight_floor
    engine = make_engine()
    client = TestClient(app)
    diffs = []
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
        families = conn.execute(text("select family_id, name from product_family order by family_id")).all()
        rounds = [
            r
            for r in conn.execute(text("select round_id, label, period_start, period_end from round order by round_id"))
            if not r[1].startswith(PREFIX)
        ]
        print(f"대상 DB: {engine.dialect.name} (읽기만) | 가중치 하한 {floor} | 제품군 {len(families)}개 x 회차 {len(rounds)}개")
        for fam_id, _fam_name in families:
            for round_id, label, start, end in rounds:
                others = [(a, b) for rid, _l, a, b in rounds if rid != round_id and a and b]
                mine = sql_numbers(conn, fam_id, start, end, others, floor)
                response = client.get(f"/api/families/{fam_id}/dashboard?round_id={round_id}")
                if response.status_code != 200:
                    diffs.append((fam_id, label, "status", response.status_code))
                    continue
                v = response.json()["voc"]
                checks = {
                    "judged": (v["counts"]["judged"], mine["judged"]),
                    "unjudged": (v["counts"]["unjudged"], mine["unjudged"]),
                    "no_text": (v["counts"]["no_text"], mine["no_text"]),
                    "total": (v["counts"]["total"], mine["judged"] + mine["unjudged"] + mine["no_text"]),
                    "failed": (v["unjudged"]["failed_count"], mine["failed"]),
                    "excluded": (v["excluded"]["count"], mine["excluded"]),
                    "excluded_other_round": (v["excluded"]["other_round_count"], mine["other"]),
                    "excluded_outside": (v["excluded"]["outside_rounds_count"], mine["excluded"] - mine["other"]),
                    "unweighted_count": (v["unweighted"]["count"], mine["judged"]),
                    "unweighted_mean": (v["unweighted"]["mean_rating"], mine["mean"]),
                    "weighted_sum": (v["weighted"]["count"], mine["w_sum"]),
                    "weighted_mean": (v["weighted"]["mean_rating"], mine["w_mean"]),
                }
                for rating in range(1, 6):
                    checks[f"dist_judged_{rating}"] = (cell_of(v["unweighted"]["rating_distribution"], rating), mine["dist"]["judged"].get(rating, 0))
                    checks[f"dist_weighted_{rating}"] = (cell_of(v["weighted"]["rating_distribution"], rating), mine["dist"]["weighted"].get(rating, 0.0))
                    checks[f"dist_unjudged_{rating}"] = (cell_of(v["unjudged"]["rating_distribution"], rating), mine["dist"]["unjudged"].get(rating, 0))
                    checks[f"dist_no_text_{rating}"] = (cell_of(v["no_text"]["rating_distribution"], rating), mine["dist"]["no_text"].get(rating, 0))
                bad = [(k, a, b) for k, (a, b) in checks.items() if not close(a, b)]
                diffs += [(fam_id, label, k, a, b) for k, a, b in bad]
                c = v["counts"]
                print(
                    f"제품군 {fam_id} {label}: 판정 {c['judged']} / 미판정 {c['unjudged']}(실패 {v['unjudged']['failed_count']}) / 제목·본문 없음 {c['no_text']} / 전체 {c['total']}"
                    f" | 포함되지 않음 {v['excluded']['count']}(다른 회차 {v['excluded']['other_round_count']}, 어느 회차에도 없음 {v['excluded']['outside_rounds_count']})"
                    f" | 비가중 평균 {v['unweighted']['mean_rating']} 가중 평균 {v['weighted']['mean_rating']} 가중 건수 {v['weighted']['count']}"
                    f" | 비교 {len(checks)}칸 중 다른 칸 {len(bad)}"
                )
    print("다른 칸 합계:", len(diffs))
    for d in diffs:
        print("  다름:", d)
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
