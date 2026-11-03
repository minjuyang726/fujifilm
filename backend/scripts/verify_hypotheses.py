"""가설 규칙(R1~R4)의 결과를 서비스 코드를 거치지 않은 SQL 집계와 다시 계산한 값으로 비교한다. 읽기 전용이고 DB에 쓰지 않는다.

backend 폴더에서 실행한다.
  python scripts/verify_hypotheses.py

- 가설은 서비스 코드(compute_snapshot + find_hypotheses)로 메모리에서만 만들고 저장하지 않는다.
- 비교: 규칙이 낸 (규칙, related_row_ids)와, SQL에서 직접 센 건수로 다시 계산한 규칙 결과가 같은지,
  related_row_ids가 스냅샷의 표에 실제로 있고 근거(허용 목록)가 비어 있지 않은지.
- 제품군 x 회차 모든 조합의 가설 목록(규칙, 종류, 진술문, related_row_ids)과 R2(R2′)에 걸린 문항(유형 포함)을 출력한다.
  진술문은 집계된 수치로 코드가 만든 문장이다. 리뷰 본문과 작성자는 읽지 않는다.
"""

import logging
import math
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
from app.services import hypotheses as h  # noqa: E402
from app.services.snapshot import compute_snapshot  # noqa: E402
from verify_voc_dashboard import PREFIX, sql_numbers  # noqa: E402

logging.disable(logging.CRITICAL)


def sql_percentages(conn, label):
    """SQL로 직접 센 {문항코드: {선택지코드: 비율(%) 소수 1자리}}, 문항 유형, 문항별 응답 수(선택지별 응답 수의 합)."""
    respondents = conn.execute(
        text("select count(*) from survey_response sr join round r on r.round_id = sr.round_id where r.label = :l"), {"l": label}
    ).scalar()
    counts = {}
    for code, value, n in conn.execute(
        text(
            "select s.code, a.value, count(distinct a.response_id) from survey_answer a "
            "join survey_question s on s.question_id = a.question_id join round r on r.round_id = s.round_id "
            "where r.label = :l group by s.code, a.value"
        ),
        {"l": label},
    ):
        counts.setdefault(code, {})[value] = n
    options = {}
    types = {}
    for code, kind, opts in conn.execute(
        text("select s.code, s.type, s.options_json from survey_question s join round r on r.round_id = s.round_id where r.label = :l"),
        {"l": label},
    ):
        types[code] = kind
        import json as _json

        parsed = opts if isinstance(opts, list) else _json.loads(opts)
        options[code] = [o["code"] for o in parsed]
    pct = {code: {o: round(counts.get(code, {}).get(o, 0) / respondents * 100, 1) for o in opts} for code, opts in options.items()}
    totals = {code: sum(counts.get(code, {}).values()) for code in options}
    return pct, types, totals


def independent_rules(pct, types, judged, mean, totals):
    """서비스 코드와 따로 쓴 규칙. 반환은 [(규칙, related_row_ids 튜플)] 우선순위 순서."""
    sat = round(pct["q01"]["4"] + pct["q01"]["5"], 1)
    out_contra, out_r2, out_r1 = [], [], []
    if sat >= 60.0 and pct["q09"]["2"] >= 50.0:
        out_contra.append(("R3", ("survey:q01:4", "survey:q01:5", "survey:q09:2")))
    if judged > 0 and mean is not None and ((sat >= 60.0 and mean <= 3.5) or (sat < 50.0 and mean >= 4.5)):
        extra = ("voc:judged:count",) if judged < VOC_SMALL_SAMPLE_THRESHOLD else ()
        out_contra.append(("R4", ("survey:q01:4", "survey:q01:5", "voc:judged:mean_unweighted") + extra))
    for code in sorted(pct):
        if types.get(code) != "single":
            continue
        ranked = sorted(pct[code].items(), key=lambda kv: (-kv[1], kv[0]))
        gap = round(ranked[0][1] - ranked[1][1], 1)
        p1, p2 = ranked[0][1] / 100, ranked[1][1] / 100
        if totals[code] > 0 and gap <= 1.96 * math.sqrt((p1 + p2 - (p1 - p2) ** 2) / totals[code]) * 100:  # R2′: 격차 <= 1.96 x SE
            out_r2.append((gap, code, ("R2", (f"survey:{code}:{ranked[0][0]}", f"survey:{code}:{ranked[1][0]}"))))
    out_r2.sort(key=lambda x: (x[0], x[1]))
    if judged < VOC_SMALL_SAMPLE_THRESHOLD:
        out_r1.append(("R1", ("voc:judged:count",)))
    return (out_contra + [x[2] for x in out_r2] + out_r1)[:5]


def main() -> int:
    settings = get_settings()
    engine = make_engine()
    diffs = []
    with engine.connect() as conn, Session(engine) as session:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SET TRANSACTION READ ONLY"))
        rounds = [r for r in session.query(Round).order_by(Round.round_id).all() if not r.label.startswith(PREFIX)]
        print(f"대상 DB: {engine.dialect.name} (읽기만, 저장하지 않음)")
        for family in session.query(ProductFamily).order_by(ProductFamily.family_id):
            for round_row in rounds:
                table, evidence = compute_snapshot(
                    session, family, round_row, weight_floor=settings.ad_weight_floor, small_sample_threshold=VOC_SMALL_SAMPLE_THRESHOLD
                )
                pct, types, totals = sql_percentages(conn, round_row.label)
                others = [(r.period_start, r.period_end) for r in rounds if r.round_id != round_row.round_id and r.period_start]
                voc = sql_numbers(conn, family.family_id, round_row.period_start, round_row.period_end, others, settings.ad_weight_floor)
                found = h.find_hypotheses(table, types)
                mine = independent_rules(pct, types, voc["judged"], voc["mean"], totals)
                got = [(x["rule"], tuple(x["related_row_ids"])) for x in found]
                rows = {r["row_id"] for r in table["rows"]}
                problems = []
                if got != mine:
                    problems.append(f"규칙 결과 다름: 서비스 {got} / SQL 재계산 {mine}")
                for x in found:
                    for rid in x["related_row_ids"]:
                        if rid not in rows:
                            problems.append(f"표에 없는 행 {rid}")
                        elif not evidence.get(rid, {}).get("ids"):
                            problems.append(f"근거가 비어 있는 행 {rid}")
                diffs += [(family.family_id, round_row.label, p) for p in problems]
                print(f"\n== 제품군 {family.family_id}({family.name}) x {round_row.label}: 가설 {len(found)}개 (SQL 재계산과 {'같음' if got == mine else '다름'}, 문제 {len(problems)}건)")
                for i, x in enumerate(found, start=1):
                    print(f"  [{i}] {x['rule']} {x['kind']} | related_row_ids {x['related_row_ids']}")
                    print(f"      {x['statement']}")
                r2 = [x for x in found if x["rule"] == "R2"]
                print(f"  R2에 걸린 문항: {[(x['related_row_ids'][0].split(':')[1], types.get(x['related_row_ids'][0].split(':')[1])) for x in r2]}")
                print(f"  R4 해당 여부: {'해당' if any(x['rule'] == 'R4' for x in found) else '해당 없음'}")
    print("\n문제 합계:", len(diffs))
    for d in diffs:
        print("  문제:", d)
    return 1 if diffs else 0


if __name__ == "__main__":
    raise SystemExit(main())
