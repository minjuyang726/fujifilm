"""가설 규칙의 임계값 민감도. 읽기 전용이고 건수와 숫자만 출력한다(리뷰 제목·본문·작성자는 읽지 않는다).

backend 폴더에서 실행한다.
  python scripts/rule_sensitivity.py

- DATABASE_URL이 가리키는 DB를 SET TRANSACTION READ ONLY 안에서 읽기만 한다. OpenAI를 부르지 않고 아무것도 저장하지 않는다.
- 제품군 x 회차 모든 조합의 스냅샷 표를 compute_snapshot으로 메모리에서 계산해, 규칙별 임계 설정마다 걸리는 가설 수를 센다.
  상한(MAX_HYPOTHESES)과 우선순위는 적용하지 않은 규칙별 개수다.
- 임계값은 모두 근거 없는 가정이다. 이 출력은 임계가 바뀔 때 결과가 어떻게 달라지는지만 보여 주며 어느 설정이 맞는지는 말하지 않는다.
"""

import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import VOC_SMALL_SAMPLE_THRESHOLD, get_settings  # noqa: E402
from app.db import make_engine  # noqa: E402
from app.models import ProductFamily, Round  # noqa: E402
from app.services import hypotheses as h  # noqa: E402
from app.services.question_step import question_types  # noqa: E402
from app.services.snapshot import compute_snapshot  # noqa: E402

logging.disable(logging.CRITICAL)
sys.stdout.reconfigure(encoding="utf-8")
PREFIX = "[파일럿-임시]"


def single_questions(table, types):
    """{문항코드: (1위 비율, 2위 비율, 문항 응답 수)}. single 유형만."""
    options = h._survey_options({row["row_id"]: row for row in table["rows"]})
    result = {}
    for code, rows in options.items():
        if types.get(code) != "single" or len(rows) < 2:
            continue
        ranked = sorted(rows, key=lambda o: (-o["pct"], o["code"]))
        result[code] = (ranked[0]["pct"], ranked[1]["pct"], sum(o["count"] for o in rows))
    return result


def main() -> int:
    settings = get_settings()
    cells = {}
    with Session(make_engine()) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        rounds = [r for r in session.query(Round).order_by(Round.round_id) if not r.label.startswith(PREFIX)]
        for family in session.query(ProductFamily).order_by(ProductFamily.family_id):
            for round_row in rounds:
                table, _evidence = compute_snapshot(
                    session, family, round_row, weight_floor=settings.ad_weight_floor, small_sample_threshold=VOC_SMALL_SAMPLE_THRESHOLD
                )
                types = question_types(session, round_row.round_id)
                rows = {row["row_id"]: row for row in table["rows"]}
                options = h._survey_options(rows)
                sat = h._satisfaction(options)
                no_pct = next((o["pct"] for o in options.get("q09", []) if o["code"] == h.NOT_RECOMMEND_OPTION), None)
                cells[(family.family_id, round_row.label)] = {
                    "judged_n": rows["voc:judged:count"]["metrics"]["건수"],
                    "mean": rows.get("voc:judged:mean_unweighted", {}).get("metrics", {}).get("평균 평점"),
                    "sat": sat[0] if sat else None,
                    "no": no_pct,
                    "singles": single_questions(table, types),
                    "found": h.find_hypotheses(table, types),
                }

    keys = list(cells)
    print("DB 읽기 전용, 저장 없음. 조합:", ", ".join(f"제품군 {k[0]} x {k[1]}" for k in keys))
    print("\n[입력 값] 조합별 판정 n, 설문 q01 4·5점 합(%), q09 아니오(%), 판정 평균 평점(비가중)")
    for k in keys:
        c = cells[k]
        print(f"  제품군 {k[0]} x {k[1]}: 판정 n={c['judged_n']}, 만족 {c['sat']}%, 비추천 {c['no']}%, 평균 평점 {c['mean']}")

    print("\n[현재 규칙의 가설] (상한·우선순위 적용 후, 규칙: 개수)")
    for k in keys:
        counts = {}
        for item in cells[k]["found"]:
            counts[item["rule"]] = counts.get(item["rule"], 0) + 1
        print(f"  제품군 {k[0]} x {k[1]}: 합계 {len(cells[k]['found'])}, {counts}, 문항 대상(R1 제외) {len(h.question_targets(cells[k]['found']))}")

    print("\n[민감도] 설정별로 걸리는 가설 수 (상한 미적용)")
    print("  " + "설정".ljust(30) + "".join(f"제품군{k[0]}x{k[1]}".ljust(18) for k in keys))

    def line(label, fn):
        print("  " + label.ljust(30) + "".join(str(fn(cells[k])).ljust(18) for k in keys))

    for threshold in (20, 30, 50):
        line(f"R1 판정 n < {threshold}", lambda c, t=threshold: int(c["judged_n"] < t))
    for gap in (3, 5, 10):
        line(f"R2 고정 격차 <= {gap}%p", lambda c, g=gap: sum(1 for p1, p2, _n in c["singles"].values() if round(p1 - p2, 1) <= g))
    line("R2′ 격차 <= 1.96xSE", lambda c: sum(1 for p1, p2, n in c["singles"].values() if h.r2_test(p1, p2, n)[2]))
    for sat_min, no_min in ((50, 40), (60, 50), (70, 60)):
        line(f"R3 만족>={sat_min} & 비추천>={no_min}", lambda c, s=sat_min, n=no_min: int(c["sat"] is not None and c["no"] is not None and c["sat"] >= s and c["no"] >= n))
    line("R4 (현재 상수)", lambda c: sum(1 for item in c["found"] if item["rule"] == "R4"))

    print("\n[R2′ 문항별 값] 격차(%p), 임계 1.96xSE(%p), 응답 수 n, R2′/고정 5%p(이전 기준) 결과")
    for k in keys:
        print(f"  제품군 {k[0]} x {k[1]}:")
        for code in sorted(cells[k]["singles"]):
            p1, p2, n = cells[k]["singles"][code]
            gap, critical, uncertain = h.r2_test(p1, p2, n)
            old = gap <= 5.0
            change = "둘 다 걸림" if uncertain and old else "R2′만 걸림(새로 걸림)" if uncertain else "이전 기준만 걸림(사라짐)" if old else "둘 다 안 걸림"
            print(f"    {code}: 1위 {p1}%, 2위 {p2}%, 격차 {gap}%p, 임계 {critical:.2f}%p, n={n} -> R2′ {'걸림' if uncertain else '-'} / 고정 5%p {'걸림' if old else '-'} ({change})")

    print("\n끝. (읽기 전용 트랜잭션, 쓰기 없음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
