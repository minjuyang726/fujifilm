"""분석 스냅샷 계산을 서비스 코드를 거치지 않은 SQL 집계와 비교한다. 읽기 전용이고 DB에 쓰지 않는다(--dry-run과 같다).

backend 폴더에서 실행한다.
  python scripts/verify_snapshot.py                                  # 제품군 x 회차 모든 조합을 비교한다
  python scripts/verify_snapshot.py --family-id 2 --round-label 2026-Q1   # 한 조합의 행 수와 q09 건수도 보여 준다

- 스냅샷은 서비스 코드(compute_snapshot)로 메모리에서만 계산하고 저장하지 않는다.
- 비교: 설문 행의 응답 수와 허용 목록 크기, VOC 행의 건수·평균·가중 합계와 허용 목록 크기.
- 숫자만 출력한다. 리뷰 본문과 작성자는 읽지 않는다.
"""

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import VOC_SMALL_SAMPLE_THRESHOLD, get_settings  # noqa: E402
from app.db import make_engine  # noqa: E402
from app.models import ProductFamily, Round  # noqa: E402
from app.services.snapshot import compute_snapshot  # noqa: E402
from verify_voc_dashboard import PREFIX, close, sql_numbers  # noqa: E402

logging.disable(logging.CRITICAL)


def sql_survey(conn, label):
    per_option = {}
    for code, value, n in conn.execute(
        text(
            "select s.code, a.value, count(distinct a.response_id) from survey_answer a "
            "join survey_question s on s.question_id = a.question_id join round r on r.round_id = s.round_id "
            "where r.label = :label group by s.code, a.value"
        ),
        {"label": label},
    ):
        per_option[(code, value)] = n
    respondents = conn.execute(
        text("select count(*) from survey_response sr join round r on r.round_id = sr.round_id where r.label = :label"),
        {"label": label},
    ).scalar()
    return per_option, respondents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--family-id", type=int)
    parser.add_argument("--round-label")
    args = parser.parse_args()

    floor = get_settings().ad_weight_floor
    engine = make_engine()
    diffs = []
    with engine.connect() as conn, Session(engine) as session:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
        families = session.query(ProductFamily).order_by(ProductFamily.family_id).all()
        rounds = [r for r in session.query(Round).order_by(Round.round_id).all() if not r.label.startswith(PREFIX)]
        print(f"대상 DB: {engine.dialect.name} (읽기만, 저장하지 않음) | 가중치 하한 {floor}")
        for family in families:
            for round_row in rounds:
                if args.family_id and family.family_id != args.family_id:
                    continue
                if args.round_label and round_row.label != args.round_label:
                    continue
                table, evidence = compute_snapshot(
                    session, family, round_row, weight_floor=floor, small_sample_threshold=VOC_SMALL_SAMPLE_THRESHOLD
                )
                rows = {r["row_id"]: r for r in table["rows"]}
                per_option, respondents = sql_survey(conn, round_row.label)
                others = [(r.period_start, r.period_end) for r in rounds if r.round_id != round_row.round_id and r.period_start]
                mine = sql_numbers(conn, family.family_id, round_row.period_start, round_row.period_end, others, floor)
                checks = {"survey:respondents": (rows["survey:respondents"]["metrics"]["응답자 수"], respondents)}
                checks["survey:respondents evidence"] = (len(evidence["survey:respondents"]["ids"]), respondents)
                survey_rows = [r for r in table["rows"] if r["row_id"].startswith("survey:q")]
                for r in survey_rows:
                    _, qcode, ocode = r["row_id"].split(":")
                    expected = per_option.get((qcode, ocode), 0)
                    checks[f"{r['row_id']} 응답 수"] = (r["metrics"]["응답 수"], expected)
                    checks[f"{r['row_id']} 허용 목록"] = (len(evidence[r["row_id"]]["ids"]), expected)
                total = mine["judged"] + mine["unjudged"] + mine["no_text"]
                checks.update(
                    {
                        "voc:total": (rows["voc:total:count"]["metrics"]["리뷰 수"], total),
                        "voc:total 허용 목록": (len(evidence["voc:total:count"]["ids"]), total),
                        "voc:judged": (rows["voc:judged:count"]["metrics"]["건수"], mine["judged"]),
                        "voc:judged 허용 목록": (len(evidence["voc:judged:count"]["ids"]), mine["judged"]),
                        "voc:unjudged": (rows["voc:unjudged:count"]["metrics"]["건수"], mine["unjudged"]),
                        "voc:unjudged 허용 목록": (len(evidence["voc:unjudged:count"]["ids"]), mine["unjudged"]),
                        "voc:unjudged 실패": (rows["voc:unjudged:count"]["metrics"]["판정 실패 건수"], mine["failed"]),
                        "voc:no_text": (rows["voc:no_text:count"]["metrics"]["건수"], mine["no_text"]),
                        "voc:no_text 허용 목록": (len(evidence["voc:no_text:count"]["ids"]), mine["no_text"]),
                        "voc:count_weighted": (rows["voc:judged:count_weighted"]["metrics"]["가중 건수"], mine["w_sum"]),
                    }
                )
                if mine["judged"]:
                    checks["voc:mean_unweighted"] = (rows["voc:judged:mean_unweighted"]["metrics"]["평균 평점"], mine["mean"])
                    checks["voc:mean_weighted"] = (rows["voc:judged:mean_weighted"]["metrics"]["가중 평균 평점"], mine["w_mean"])
                for rating in range(1, 6):
                    checks[f"voc:dist_unweighted:{rating}"] = (rows[f"voc:judged:dist_unweighted:{rating}"]["metrics"]["건수"], mine["dist"]["judged"].get(rating, 0))
                    checks[f"voc:dist_weighted:{rating}"] = (rows[f"voc:judged:dist_weighted:{rating}"]["metrics"]["가중 건수"], mine["dist"]["weighted"].get(rating, 0.0))
                bad = [(k, a, b) for k, (a, b) in checks.items() if not close(a, b)]
                diffs += [(family.family_id, round_row.label, k, a, b) for k, a, b in bad]
                print(
                    f"제품군 {family.family_id} {round_row.label}: 행 {len(table['rows'])}개(설문 {sum(1 for r in table['rows'] if r['group'] == '설문')}, VOC {sum(1 for r in table['rows'] if r['group'] == 'VOC')})"
                    f" | 허용 목록 ID 합계 {sum(len(v['ids']) for v in evidence.values())} | 비교 {len(checks)}칸 중 다른 칸 {len(bad)}"
                )
                if args.family_id and args.round_label:
                    for qrow in ("survey:q09:1", "survey:q09:2"):
                        r = rows[qrow]
                        print(f"  {qrow}: 응답 수 {r['metrics']['응답 수']}, 비율 {r['metrics']['비율(%)']}%, 허용 목록 {len(evidence[qrow]['ids'])}건, 출처 {r['source']}")
                    print(f"  voc:judged:count: 건수 {rows['voc:judged:count']['metrics']['건수']}, 표본 적음 {rows['voc:judged:count']['small_sample']}")
    print("다른 칸 합계:", len(diffs))
    for d in diffs:
        print("  다름:", d)
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
