"""데이터 품질 점검. 읽기 전용이고 건수와 ID만 출력한다(리뷰 제목·본문·작성자는 출력하지 않는다).

backend 폴더에서 실행한다.
  python scripts/audit_data_quality.py

- DATABASE_URL이 가리키는 DB를 SET TRANSACTION READ ONLY 안에서 읽기만 한다. OpenAI를 부르지 않는다.
- 제목과 본문은 메모리에서 길이·공백 여부·같은 문자열인지 비교하는 데만 쓰고 출력하지 않는다.
- 점검 항목: 중복 후보, 평점·날짜, 제품 연결, 본문 길이와 없음 비율, 회차별 리뷰 수, 합성 설문의 무결성,
  두 제품군 설문 수치 비교, 본문 1자 글, 본문 문자열이 같은 글, 설문 확률표 대비 생성 빈도,
  상품별 월·분기별 건수, 윌슨 신뢰구간.
"""

import logging
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.models import (  # noqa: E402
    AnalysisSnapshot, Product, Review, Round, SurveyAnswer, SurveyQuestion, SurveyResponse,
)
from app.services import synthetic_survey as ss  # noqa: E402

logging.disable(logging.CRITICAL)
sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔과 파일 리다이렉트에서 한글이 깨지지 않게 한다


def blank(value):
    return value is None or str(value).strip() == ""


def wilson(k, n, z=1.96):
    """95% 윌슨 점수 구간. p = k/n, 중심 = (p + z²/2n) / (1 + z²/n), 반폭 = z·sqrt(p(1−p)/n + z²/4n²) / (1 + z²/n)."""
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, center - half, center + half


def show_wilson(label, k, n):
    p, lo, hi = wilson(k, n)
    print(f"  {label}: {k}/{n} = {p:.1%}, 95% 윌슨 구간 {lo:.1%} ~ {hi:.1%}")


def by_family(counter, key=lambda x: (x[0] is None, x[0])):
    return sorted(counter.items(), key=key)


def main():
    today = date.today()
    with Session(make_engine()) as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        rows = list(s.execute(select(
            Review.review_id, Review.product_name, Review.rating, Review.date, Review.title, Review.review_text
        )))
        products = {p.product_name: p.family_id for p in s.scalars(select(Product))}
        n = len(rows)
        print(f"[기본] review 행 {n} | product 행 {len(products)} | 오늘 {today}")

        # 1. 중복 후보
        print("\n== 1. 중복 후보 ==")
        groups, groups_no = defaultdict(list), defaultdict(list)
        for r in rows:
            key = (r.product_name, r.date, r.rating, (r.title or "").strip(), (r.review_text or "").strip())
            (groups_no if blank(r.title) and blank(r.review_text) else groups)[key].append(r.review_id)
        dup = {k: v for k, v in groups.items() if len(v) > 1}
        ids = sorted(i for v in dup.values() for i in v)
        print(f"제목·본문 있는 글: 같은 (상품,날짜,평점,제목,본문) 묶음 {len(dup)}개, review 수 {len(ids)}, review_id(최대 20) {ids[:20]}")
        for label, pick in (("본문만 같음", lambda r: r.review_text), ("제목만 같음", lambda r: r.title)):
            g = defaultdict(list)
            for r in rows:
                if not blank(pick(r)):
                    g[(r.product_name, r.date, r.rating, pick(r).strip())].append(r.review_id)
            d = {k: v for k, v in g.items() if len(v) > 1}
            print(f"  {label}(상품,날짜,평점 동일): 묶음 {len(d)}, review 수 {sum(len(v) for v in d.values())}")
        dn = {k: v for k, v in groups_no.items() if len(v) > 1}
        print(f"제목·본문 둘 다 없는 글(참고, 같은 상품·날짜·평점): 묶음 {len(dn)}, review 수 {sum(len(v) for v in dn.values())}, 최대 묶음 크기 {max((len(v) for v in dn.values()), default=0)} (내용이 없어 같은 글인지 판단 불가)")

        # 2. 평점·날짜
        print("\n== 2. 평점·날짜 ==")
        rc = Counter(r.rating for r in rows)
        print("평점 분포:", sorted(rc.items()), "| 1~5 밖:", sum(v for k, v in rc.items() if k is None or k < 1 or k > 5))
        dates = [r.date for r in rows if r.date is not None]
        print(f"날짜 NULL {n - len(dates)} | 최소 {min(dates)} | 최대 {max(dates)} | 미래(>{today}) {sum(1 for d in dates if d > today)}")
        print("연도별 건수:", sorted(Counter(d.year for d in dates).items()))

        # 3. 제품 연결
        print("\n== 3. product 연결 ==")
        missing = [r.review_id for r in rows if r.product_name not in products]
        nofam = [r.review_id for r in rows if r.product_name in products and products[r.product_name] is None]
        print(f"product에 없는 product_name 리뷰 {len(missing)} {missing[:20]} | family_id NULL 리뷰 {len(nofam)} {nofam[:20]}")
        print("제품군별 리뷰 수:", by_family(Counter(products.get(r.product_name) for r in rows)))

        # 4. 본문 길이
        print("\n== 4. 본문 길이·없음 비율 ==")
        lens = [len(r.review_text.strip()) for r in rows if not blank(r.review_text)]
        print(f"본문 있는 글 {len(lens)} | 길이(글자) 최소 {min(lens)} 중앙값 {statistics.median(lens)} 최대 {max(lens)}")
        no_both = [r for r in rows if blank(r.title) and blank(r.review_text)]
        no_text = [r for r in rows if blank(r.review_text)]
        no_title = [r for r in rows if blank(r.title)]
        print(f"제목·본문 둘 다 없음 {len(no_both)} ({len(no_both)/n:.1%}) | 본문 없음 {len(no_text)} ({len(no_text)/n:.1%}) | 제목 없음 {len(no_title)} ({len(no_title)/n:.1%}) | 제목 또는 본문 있음 {n - len(no_both)}")
        print("평점별 (건수 / 제목·본문 없음 / 비율 / 본문 없음 비율):")
        for k in sorted(rc):
            nb = sum(1 for r in no_both if r.rating == k)
            nt = sum(1 for r in no_text if r.rating == k)
            print(f"  평점 {k}: {rc[k]} / {nb} / {nb / rc[k]:.1%} / {nt / rc[k]:.1%}")

        # 5. 회차
        print("\n== 5. 회차별 리뷰 ==")
        all_rounds = list(s.scalars(select(Round).order_by(Round.round_id)))
        rounds = [rd for rd in all_rounds if rd.period_start and rd.period_end]
        for rd in all_rounds:
            print(f"round {rd.round_id} {rd.label} {rd.period_start}~{rd.period_end}")
        print("기간이 없는 회차(제외):", [rd.label for rd in all_rounds if rd not in rounds])
        inside = set()
        cell_total, cell_text = {}, {}
        for rd in rounds:
            tot, txt = Counter(), Counter()
            for r in rows:
                if r.date is not None and rd.period_start <= r.date <= rd.period_end:
                    fam = products.get(r.product_name)
                    tot[fam] += 1
                    inside.add(r.review_id)
                    if not (blank(r.title) and blank(r.review_text)):
                        txt[fam] += 1
            cell_total[rd.label], cell_text[rd.label] = tot, txt
            print(f"  {rd.label} 제품군별 리뷰 수 {by_family(tot)} 합 {sum(tot.values())} | 제목 또는 본문이 있는 글 {by_family(txt)} 합 {sum(txt.values())}")
        outside = [r for r in rows if r.review_id not in inside]
        print(f"회차 밖 리뷰 {len(outside)} ({len(outside)/n:.1%}) | 회차 안 {len(inside)}")
        first_start = min(rd.period_start for rd in rounds)
        last_end = max(rd.period_end for rd in rounds)
        print(f"  회차 이전 {sum(1 for r in outside if r.date < first_start)} | 회차 이후 {sum(1 for r in outside if r.date > last_end)}")

        # 6, 7. 합성 설문 무결성
        print("\n== 6·7. 합성 설문 무결성 ==")
        qs = list(s.scalars(select(SurveyQuestion).order_by(SurveyQuestion.round_id, SurveyQuestion.code)))
        resp = list(s.scalars(select(SurveyResponse)))
        ans = list(s.execute(select(SurveyAnswer.response_id, SurveyAnswer.question_id, SurveyAnswer.value)))
        for rd in rounds:
            rr = [x for x in resp if x.round_id == rd.round_id]
            qr = [q for q in qs if q.round_id == rd.round_id]
            print(f"{rd.label}: 응답 {len(rr)} (is_synthetic 거짓 {sum(1 for x in rr if not x.is_synthetic)}, family_id NOT NULL {sum(1 for x in rr if x.family_id is not None)}) | 문항 {len(qr)}")
            by_resp = defaultdict(lambda: defaultdict(list))
            qid_set = {q.question_id for q in qr}
            for a in ans:
                if a.question_id in qid_set:
                    by_resp[a.response_id][a.question_id].append(a.value)
            miss = [x.response_id for x in rr if any(q.question_id not in by_resp[x.response_id] for q in qr)]
            bad, single_bad, dup_bad, excl_bad = [], 0, 0, 0
            for q in qr:
                allowed = {o["code"] for o in q.options_json}
                for x in rr:
                    vals = by_resp[x.response_id].get(q.question_id, [])
                    bad += [(x.response_id, q.code) for v in vals if v not in allowed]
                    dup_bad += len(vals) != len(set(vals))
                    single_bad += q.type != "multi" and len(vals) > 1
                    excl_bad += q.type == "multi" and "5" in vals and len(vals) > 1
            print(f"  10문항 중 누락 있는 응답자 {len(miss)} {miss[:20]} | 보기 밖 값 {len(bad)} {bad[:10]} | 단일문항 2개 이상 {single_bad} | 같은 값 중복 {dup_bad} | 배타 보기 위반 {excl_bad}")
        resp_round = {x.response_id: x.round_id for x in resp}
        q_round = {q.question_id: q.round_id for q in qs}
        print(f"답 총 {len(ans)} | 문항이 없는 답 {sum(1 for a in ans if a.question_id not in q_round)} | 응답 회차≠문항 회차 {sum(1 for a in ans if a.response_id in resp_round and a.question_id in q_round and resp_round[a.response_id] != q_round[a.question_id])} | 응답이 없는 답 {sum(1 for a in ans if a.response_id not in resp_round)}")

        # 8. 두 제품군 설문 수치
        print("\n== 8. 두 제품군 설문 수치 비교 ==")
        print("survey_response.family_id 분포 (SQL):", s.execute(text("select family_id, count(*) from survey_response group by family_id")).all())
        snaps = {}
        for sn in s.scalars(select(AnalysisSnapshot).order_by(AnalysisSnapshot.snapshot_id)):
            snaps[(sn.family_id, sn.round_id)] = sn
        for rd in rounds:
            a, b = snaps.get((1, rd.round_id)), snaps.get((2, rd.round_id))
            if not a or not b:
                print(f"{rd.label}: 스냅샷 없음 (제품군1 {bool(a)}, 제품군2 {bool(b)})")
                continue
            sa = {r["row_id"]: r["metrics"] for r in a.table_json["rows"] if r["row_id"].startswith("survey:")}
            sb = {r["row_id"]: r["metrics"] for r in b.table_json["rows"] if r["row_id"].startswith("survey:")}
            ea = {k: v["ids"] for k, v in a.allowed_evidence_json.items() if k.startswith("survey:")}
            eb = {k: v["ids"] for k, v in b.allowed_evidence_json.items() if k.startswith("survey:")}
            sql_rows = s.execute(text(
                "select q.code, a.value, count(distinct a.response_id) from survey_answer a "
                "join survey_question q on q.question_id=a.question_id join survey_response r on r.response_id=a.response_id "
                "where q.round_id=:r and r.round_id=:r group by q.code, a.value"), {"r": rd.round_id}).all()
            sqlcnt = {f"survey:{c}:{v}": cnt for c, v, cnt in sql_rows}
            diff = sum(1 for k, m in sa.items() if k.startswith("survey:q") and next((v for kk, v in m.items() if "응답 수" in kk), None) != sqlcnt.get(k, 0))
            print(f"{rd.label}: 스냅샷 제품군1 #{a.snapshot_id}, 제품군2 #{b.snapshot_id} | 설문 행 {len(sa)} vs {len(sb)} | 행 id 동일 {set(sa) == set(sb)} | metrics 다른 행 {sum(1 for k in sa if sa[k] != sb.get(k))} | 근거 응답 ID 다른 행 {sum(1 for k in ea if ea[k] != eb.get(k))} | SQL 재계산 대비 다른 칸 {diff}")

        # 9. 본문 1자 글 / 본문 문자열이 같은 글
        print("\n== 9. 본문 1자 글, 본문 문자열이 같은 글 ==")
        one = [r for r in rows if not blank(r.review_text) and len(r.review_text.strip()) == 1]
        print(f"본문 길이 1자: {len(one)}건 | 평점 분포 {sorted(Counter(r.rating for r in one).items())} | review_id {sorted(r.review_id for r in one)[:20]}")
        same = defaultdict(list)
        for r in rows:
            if not blank(r.review_text):
                same[r.review_text.strip()].append(r)
        for members in same.values():
            if len(members) > 1:
                print(f"  본문 문자열이 같은 {len(members)}건:")
                for r in sorted(members, key=lambda x: x.review_id):
                    print(f"    review_id {r.review_id} | 상품 {r.product_name} | 날짜 {r.date} | 평점 {r.rating} | 본문 길이 {len(r.review_text.strip())}")

        # 10. 설문 확률표 대비 생성 빈도
        print("\n== 10. 설문 확률표 대비 DB 생성 빈도 (문항 × 보기, 응답 100건 기준) ==")
        cells = []
        for rd in rounds:
            qr = {q.code: q for q in qs if q.round_id == rd.round_id}
            n_resp = sum(1 for x in resp if x.round_id == rd.round_id)
            counts = Counter()
            seen = set()
            for a in ans:
                q = next((qq for qq in qr.values() if qq.question_id == a.question_id), None)
                if q is not None and (a.response_id, q.question_id, a.value) not in seen:
                    seen.add((a.response_id, q.question_id, a.value))
                    counts[(q.code, a.value)] += 1
            for code, _text, kind, options in ss.QUESTIONS:
                if kind == "multi":
                    tbl = ss.MULTI_TABLES[rd.label][code]
                    inc = tbl["p_include"]
                    p_none_chosen = 1 - math.prod(1 - p for p in inc)
                    # 아무것도 안 골라지면 p_include 비율로 하나를 고른다
                    expected = [(1 - tbl["p_none"]) * (p + (1 - p_none_chosen) * p / sum(inc)) for p in inc] + [tbl["p_none"]]
                else:
                    expected = ss.PROBABILITY_TABLES[rd.label][code]
                for i, e in enumerate(expected, start=1):
                    realized = counts[(code, str(i))] / n_resp
                    cells.append((abs(realized - e) * 100, rd.label, code, i, e, realized))
        top = sorted(cells, reverse=True)[:3]
        print(f"비교 칸 {len(cells)}개 | 최대 절대 차이 {top[0][0]:.1f}%p | 평균 절대 차이 {statistics.mean(c[0] for c in cells):.2f}%p")
        print("가장 큰 차이 3칸 (회차, 문항, 보기 번호, 확률표 기대, DB 빈도, 차이%p):")
        for diff, label, code, i, e, realized in top:
            print(f"  {label} {code} 보기 {i}: 기대 {e:.1%}, DB {realized:.1%}, 차이 {diff:.1f}%p")
        print("  (q08 다중선택의 기대값은 코드의 추출 규칙에서 계산한 주변 확률이다)")

        # 11. 상품별 월·분기별 건수
        print("\n== 11. 상품별 월별·분기별 건수 (전체 / 제목 또는 본문 있는 글) ==")
        first, last = min(dates), max(dates)
        months = []
        y, m = first.year, first.month
        while (y, m) <= (last.year, last.month):
            months.append((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        print(f"기간 {first.year}-{first.month:02d} ~ {last.year}-{last.month:02d} ({len(months)}개월). 칸은 '전체/텍스트 있음', 0건은 '-'")
        for name in sorted(products):
            mine = [r for r in rows if r.product_name == name]
            tot, txt = Counter(), Counter()
            for r in mine:
                tot[(r.date.year, r.date.month)] += 1
                txt[(r.date.year, r.date.month)] += not (blank(r.title) and blank(r.review_text))
            qt, qx = Counter(), Counter()
            for (yy, mm), v in tot.items():
                qt[(yy, (mm - 1) // 3 + 1)] += v
                qx[(yy, (mm - 1) // 3 + 1)] += txt[(yy, mm)]
            print(f"\n[상품] {name} (제품군 {products[name]}) | 리뷰 {len(mine)} | 제목 또는 본문 있음 {sum(txt.values())}")
            print("  월별:")
            for yy in range(first.year, last.year + 1):
                cells_m = [f"{tot[(yy, mm)]}/{txt[(yy, mm)]}" if tot[(yy, mm)] else "-" for mm in range(1, 13)]
                print(f"    {yy}: " + " ".join(f"{c:>5}" for c in cells_m))
            print("  분기별:")
            for yy in range(first.year, last.year + 1):
                cells_q = [f"{qt[(yy, qq)]}/{qx[(yy, qq)]}" if qt[(yy, qq)] else "-" for qq in range(1, 5)]
                print(f"    {yy}: " + " ".join(f"{c:>6}" for c in cells_q))
            month_text = [txt[mo] for mo in months]
            n_q = [(yy, qq) for yy in range(first.year, last.year + 1) for qq in range(1, 5) if (yy, qq) >= (first.year, (first.month - 1) // 3 + 1) and (yy, qq) <= (last.year, (last.month - 1) // 3 + 1)]
            print(f"  전체 기간: 텍스트 글이 0건인 달 {sum(1 for v in month_text if v == 0)}/{len(months)}개월, 0건인 분기 {sum(1 for k in n_q if qx[k] == 0)}/{len(n_q)}분기")
            recent_m = months[-12:]
            vals_m = [txt[mo] for mo in recent_m]
            recent_q = [(2025, 4), (2026, 1), (2026, 2), (2026, 3)]
            vals_q = [qx[k] for k in recent_q]
            print(f"  최근 12개월({recent_m[0][0]}-{recent_m[0][1]:02d}~{recent_m[-1][0]}-{recent_m[-1][1]:02d}, 마지막 달은 {last.day}일까지): 월별 텍스트 글 {vals_m} | 최소 {min(vals_m)} 중앙값 {statistics.median(vals_m)} 최대 {max(vals_m)} | 합 {sum(vals_m)}")
            print(f"  완결 분기 4개(2025Q4~2026Q3): 분기별 텍스트 글 {vals_q} | 최소 {min(vals_q)} 중앙값 {statistics.median(vals_q)} 최대 {max(vals_q)} | 합 {sum(vals_q)}")

        # 12. 윌슨 신뢰구간
        print("\n== 12. 95% 윌슨 신뢰구간 ==")
        print("  식: p = k/n, 중심 = (p + z²/2n)/(1 + z²/n), 반폭 = z·sqrt(p(1−p)/n + z²/4n²)/(1 + z²/n), z = 1.96")
        show_wilson("회차 밖 리뷰", len(outside), n)
        show_wilson("제목·본문 둘 다 없음", len(no_both), n)
        show_wilson("5점", rc[5], n)
        show_wilson("1점 중 제목·본문 없음", sum(1 for r in no_both if r.rating == 1), rc[1])
        for rd in rounds:
            for fam, total in by_family(cell_total[rd.label]):
                show_wilson(f"{rd.label} 제품군 {fam}의 제목 또는 본문이 있는 글 비율", cell_text[rd.label][fam], total)

    print("\n끝. (읽기 전용 트랜잭션, 쓰기 없음)")


if __name__ == "__main__":
    main()
