"""불확실·모순 가설 찾기(G5, 결정 2026-11-03). 코드 규칙만 쓰고 LLM은 관여하지 않는다(FR-0.1).

입력은 스냅샷의 표(table_json)와 문항 유형이다(유형은 표에 없어서 survey_question에서 읽어 넘긴다). 진술문은 코드가 템플릿으로 만들고
related_row_ids를 붙인다. 설문 행에 기반한 진술문에는 "합성", 표본 적음에 기반한 진술문에는 "표본"이 들어간다.

규칙과 임계값은 모두 근거 없는 임시 가정이다(Q-7처럼 이 데이터로 검증하지 않았다).
- R1 uncertain: 판정 묶음의 n이 표본 적음 기준(app/config.py VOC_SMALL_SAMPLE_THRESHOLD, 표의 `small_sample`과 `표본 적음 기준(건)`으로 읽는다) 미만이다.
- R2 uncertain: single 유형 문항에서 1위와 2위 선택지의 비율 차이가 R2_MAX_GAP_PP 이하다.
  scale5는 점수형이라 인접 점수가 경쟁하는 선택지가 아니고, multi는 비율의 합이 100%를 넘어 순위 비교가 맞지 않아 뺀다.
- R3 contradictory: 전반 만족도(q01)의 4·5점 비율 합 >= R3_SATISFACTION_MIN 이고 추천 경험(q09)의 "아니오" 비율 >= R3_NOT_RECOMMEND_MIN.
- R4 contradictory: q01의 4·5점 비율 합(만족)이 R4_SATISFACTION_HIGH 이상인데 VOC 판정 묶음의 비가중 평균 평점이 R4_VOC_MEAN_LOW 이하이거나,
  만족이 R4_SATISFACTION_LOW 미만인데 평균 평점이 R4_VOC_MEAN_HIGH 이상이다(판정이 1건 이상일 때만). 현재 데이터에서는 해당 없다.
우선순위: contradictory(R3, R4) > R2(차이가 작은 순) > R1. 최대 MAX_HYPOTHESES개.
R3·R4의 q01, q09는 합성 설문의 문항 코드다(app/services/synthetic_survey.py).
"""

MAX_HYPOTHESES = 5
R2_MAX_GAP_PP = 5.0
R3_SATISFACTION_MIN = 60.0
R3_NOT_RECOMMEND_MIN = 50.0
R4_SATISFACTION_HIGH = 60.0
R4_VOC_MEAN_LOW = 3.5
R4_SATISFACTION_LOW = 50.0
R4_VOC_MEAN_HIGH = 4.5

SATISFACTION_QUESTION = "q01"
SATISFACTION_OPTIONS = ("4", "5")  # 만족, 매우 만족
RECOMMEND_QUESTION = "q09"
NOT_RECOMMEND_OPTION = "2"  # 아니오

KIND_UNCERTAIN = "uncertain"
KIND_CONTRADICTORY = "contradictory"


def _split_item(item: str) -> tuple[str, str]:
    question, _, option = item.partition(" — ")
    return question.strip(), option.strip()


def _survey_options(rows_by_id: dict) -> dict[str, list[dict]]:
    """문항 코드 -> 선택지 행 목록. 각 원소는 {code, option, question_text, pct, row_id}."""
    grouped: dict[str, list[dict]] = {}
    for row_id, row in rows_by_id.items():
        parts = row_id.split(":")
        if len(parts) != 3 or parts[0] != "survey" or parts[1] == "respondents":
            continue
        question_text, option = _split_item(row["item"])
        grouped.setdefault(parts[1], []).append(
            {"code": parts[2], "option": option, "question_text": question_text, "pct": row["metrics"]["비율(%)"], "row_id": row_id}
        )
    return grouped


def _satisfaction(options: dict[str, list[dict]]) -> tuple[float, list[dict]] | None:
    rows = [o for o in options.get(SATISFACTION_QUESTION, []) if o["code"] in SATISFACTION_OPTIONS]
    if len(rows) != len(SATISFACTION_OPTIONS):
        return None
    rows.sort(key=lambda o: o["code"])
    return round(sum(o["pct"] for o in rows), 1), rows


def find_hypotheses(table: dict, question_types: dict[str, str]) -> list[dict]:
    """[{rule, kind, statement, related_row_ids}] 를 우선순위 순서로, 최대 MAX_HYPOTHESES개 돌려준다."""
    rows_by_id = {row["row_id"]: row for row in table["rows"]}
    options = _survey_options(rows_by_id)
    sat = _satisfaction(options)
    judged = rows_by_id.get("voc:judged:count")
    mean_row = rows_by_id.get("voc:judged:mean_unweighted")
    contradictory: list[dict] = []
    uncertain_r2: list[tuple[float, str, dict]] = []
    uncertain_r1: list[dict] = []

    # ---- R3 ----
    recommend = {o["code"]: o for o in options.get(RECOMMEND_QUESTION, [])}.get(NOT_RECOMMEND_OPTION)
    if sat is not None and recommend is not None:
        sat_pct, sat_rows = sat
        if sat_pct >= R3_SATISFACTION_MIN and recommend["pct"] >= R3_NOT_RECOMMEND_MIN:
            q_text = sat_rows[0]["question_text"]
            contradictory.append(
                {
                    "rule": "R3",
                    "kind": KIND_CONTRADICTORY,
                    "statement": (
                        f"합성 설문의 '{q_text}'에서 '{sat_rows[0]['option']}'·'{sat_rows[1]['option']}' 응답이 합쳐 {sat_pct}%인데, "
                        f"'{recommend['question_text']}'에서 '{recommend['option']}' 응답이 {recommend['pct']}%로 만족과 추천 경험이 어긋난다."
                    ),
                    "related_row_ids": [o["row_id"] for o in sat_rows] + [recommend["row_id"]],
                }
            )

    # ---- R4 ----
    if sat is not None and mean_row is not None and judged is not None and judged["metrics"]["건수"] > 0:
        sat_pct, sat_rows = sat
        mean = mean_row["metrics"]["평균 평점"]
        mismatch = (sat_pct >= R4_SATISFACTION_HIGH and mean <= R4_VOC_MEAN_LOW) or (
            sat_pct < R4_SATISFACTION_LOW and mean >= R4_VOC_MEAN_HIGH
        )
        if mismatch:
            small = " 표본이 적은" if judged["small_sample"] else ""
            contradictory.append(
                {
                    "rule": "R4",
                    "kind": KIND_CONTRADICTORY,
                    "statement": (
                        f"합성 설문의 전반 만족(상위 두 선택지 합)은 {sat_pct}%인데 실측 VOC{small} 판정 묶음의 평균 평점은 {mean}으로 설문과 VOC가 어긋난다."
                    ),
                    "related_row_ids": [o["row_id"] for o in sat_rows] + ["voc:judged:mean_unweighted"]
                    + (["voc:judged:count"] if judged["small_sample"] else []),
                }
            )

    # ---- R2 ----
    for code in sorted(options):
        if question_types.get(code) != "single":
            continue
        ranked = sorted(options[code], key=lambda o: (-o["pct"], o["code"]))
        if len(ranked) < 2:
            continue
        first, second = ranked[0], ranked[1]
        gap = round(first["pct"] - second["pct"], 1)
        if gap <= R2_MAX_GAP_PP:
            uncertain_r2.append(
                (
                    gap,
                    code,
                    {
                        "rule": "R2",
                        "kind": KIND_UNCERTAIN,
                        "statement": (
                            f"합성 설문의 '{first['question_text']}'에서 1위는 '{first['option']}'({first['pct']}%), "
                            f"2위는 '{second['option']}'({second['pct']}%)로 차이가 {gap}%p로 작아 우세한 응답이 불확실하다."
                        ),
                        "related_row_ids": [first["row_id"], second["row_id"]],
                    },
                )
            )
    uncertain_r2.sort(key=lambda item: (item[0], item[1]))

    # ---- R1 ----
    if judged is not None and judged["small_sample"]:
        n = judged["metrics"]["건수"]
        threshold = judged["metrics"]["표본 적음 기준(건)"]
        uncertain_r1.append(
            {
                "rule": "R1",
                "kind": KIND_UNCERTAIN,
                "statement": f"실측 VOC 판정 묶음이 {n}건으로 표본이 적어(기준 {threshold}건 미만) VOC 평점을 해석하기 어렵다.",
                "related_row_ids": ["voc:judged:count"],
            }
        )

    ordered = contradictory + [item for _, _, item in uncertain_r2] + uncertain_r1
    return ordered[:MAX_HYPOTHESES]
