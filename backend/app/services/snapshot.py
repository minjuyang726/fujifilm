"""분석 스냅샷 계산(step analysis-snapshot). LLM을 쓰지 않는다. 계산은 코드가 한다(FR-0.1, 0.2).

제품군 x 회차마다 표 하나를 만든다. 행 구성(Phase 5 설계, spec.md 3.2 analysis_snapshot):
- 설문 행(source "합성"): `survey:respondents`, 문항 x 선택지마다 `survey:{문항코드}:{선택지코드}` (응답 수, 비율(%), 선택지 번호).
- VOC 행(source "실측"): `voc:total:count`, `voc:judged:count`, `voc:unjudged:count`, `voc:no_text:count`,
  `voc:judged:mean_unweighted`, `voc:judged:mean_weighted`, `voc:judged:count_weighted`,
  `voc:judged:dist_unweighted:{1..5}`, `voc:judged:dist_weighted:{1..5}`.
- 근거(SP-3): 설문 행은 그 행에 들어간 response_id, VOC 행은 그 행에 들어간 review_id. 표(LLM 입력)와 따로 `allowed_evidence`에 둔다.
같은 입력이면 같은 결과가 나오도록 정렬하고 소수 자리를 고정한다. 리뷰 본문과 작성자는 읽지 않는다.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProductFamily, Round, SurveyAnswer, SurveyQuestion, SurveyResponse
from app.services.dashboard import survey_section
from app.services.voc import build_voc

SOURCE_SURVEY = "합성"
SOURCE_VOC = "실측"


def _row(row_id: str, group: str, source: str, item: str, metrics: dict, small_sample: bool = False) -> dict:
    return {"row_id": row_id, "group": group, "source": source, "item": item, "metrics": metrics, "small_sample": small_sample}


def _percent(count: float, total: float) -> float:
    return round(count / total * 100, 1) if total else 0.0


def compute_snapshot(
    session: Session, family: ProductFamily, round_row: Round, *, weight_floor: float, small_sample_threshold: int
) -> tuple[dict, dict]:
    """(table_json, allowed_evidence_json)를 돌려준다."""
    rows: list[dict] = []
    evidence: dict[str, dict] = {}

    # ---- 설문 ----
    survey = survey_section(session, round_row.round_id)
    source = survey["synthetic_label"] or "설문"
    response_ids = sorted(
        session.scalars(select(SurveyResponse.response_id).where(SurveyResponse.round_id == round_row.round_id))
    )
    respondents = survey["respondent_count"]
    rows.append(_row("survey:respondents", "설문", source, "설문 응답자 수", {"응답자 수": respondents}))
    evidence["survey:respondents"] = {"kind": "survey", "ids": response_ids}

    questions = session.scalars(
        select(SurveyQuestion).where(SurveyQuestion.round_id == round_row.round_id).order_by(SurveyQuestion.question_id)
    ).all()
    chosen: dict[tuple[int, str], list[int]] = {}
    for question_id, response_id, value in session.execute(
        select(SurveyAnswer.question_id, SurveyAnswer.response_id, SurveyAnswer.value)
        .join(SurveyQuestion, SurveyQuestion.question_id == SurveyAnswer.question_id)
        .where(SurveyQuestion.round_id == round_row.round_id)
    ):
        chosen.setdefault((question_id, value), []).append(response_id)
    by_question = {q["question_id"]: q for q in survey["questions"]}
    for question in questions:
        for result in by_question[question.question_id]["results"]:
            row_id = f"survey:{question.code}:{result['code']}"
            rows.append(
                _row(
                    row_id,
                    "설문",
                    source,
                    f"{question.text} — {result['option']}",
                    {
                        "응답 수": result["count"],
                        "비율(%)": _percent(result["count"], respondents),
                        "선택지 번호": int(result["code"]) if result["code"].isdigit() else result["code"],
                    },
                )
            )
            evidence[row_id] = {"kind": "survey", "ids": sorted(chosen.get((question.question_id, result["code"]), []))}

    # ---- 외부 VOC ----
    voc, ids = build_voc(
        session, family.family_id, round_row, weight_floor=weight_floor, small_sample_threshold=small_sample_threshold
    )
    counts = voc["counts"]
    small = voc["small_sample"]

    def add_voc(row_id: str, item: str, metrics: dict, id_key: str, small_sample: bool = False) -> None:
        rows.append(_row(row_id, "VOC", SOURCE_VOC, item, metrics, small_sample))
        evidence[row_id] = {"kind": "review", "ids": ids[id_key]}

    add_voc("voc:total:count", "VOC 전체 리뷰(선택한 제품군·회차)", {"리뷰 수": counts["total"]}, "total")
    add_voc(
        "voc:judged:count",
        "판정 묶음(광고성 판정에 성공한 글)",
        {"건수": counts["judged"], "표본 적음 기준(건)": voc["small_sample_threshold"]},
        "judged",
        small,
    )
    add_voc(
        "voc:unjudged:count",
        "미판정 묶음(판정 대상이지만 성공한 판정이 없는 글)",
        {"건수": counts["unjudged"], "판정 실패 건수": voc["unjudged"]["failed_count"]},
        "unjudged",
    )
    add_voc("voc:no_text:count", "제목·본문 없음 묶음", {"건수": counts["no_text"]}, "no_text")
    if voc["unweighted"]["mean_rating"] is not None:
        add_voc("voc:judged:mean_unweighted", "판정 묶음 평균 평점(비가중)", {"평균 평점": voc["unweighted"]["mean_rating"]}, "judged", small)
        add_voc(
            "voc:judged:mean_weighted",
            "판정 묶음 가중 평균 평점",
            {"가중 평균 평점": voc["weighted"]["mean_rating"], "가중치 하한": voc["weight_floor"]},
            "judged",
            small,
        )
    add_voc("voc:judged:count_weighted", "판정 묶음 가중 건수(가중치의 합)", {"가중 건수": voc["weighted"]["count"]}, "judged", small)
    judged_n = counts["judged"]
    for cell in voc["unweighted"]["rating_distribution"]:
        add_voc(
            f"voc:judged:dist_unweighted:{cell['rating']}",
            f"판정 묶음 평점 {cell['rating']}점(비가중)",
            {"평점": cell["rating"], "건수": int(cell["count"]), "비율(%)": _percent(cell["count"], judged_n)},
            "judged",
            small,
        )
    for cell in voc["weighted"]["rating_distribution"]:
        add_voc(
            f"voc:judged:dist_weighted:{cell['rating']}",
            f"판정 묶음 평점 {cell['rating']}점(가중)",
            {"평점": cell["rating"], "가중 건수": cell["count"]},
            "judged",
            small,
        )

    table = {"family": family.name, "round": round_row.label, "rows": rows}
    return table, evidence
