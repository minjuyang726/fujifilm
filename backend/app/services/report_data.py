"""리포트 조회·조립용 읽기 함수(A-5, A-6, A-7, report-assembly). 읽기 전용이다.

- 최신 리포트 = 제품군 x 회차에서 성공한 action-suggestions로 만들어진 가장 최근 report(report는 성공한 실행에서만 만든다).
- 최신 초안 = 해당 report의 next_survey_question 중 가장 큰 run_id의 것(결정 2026-11-03). 초안이 없으면 문항 목록이 비어 있다.
- 리뷰 본문과 작성자는 읽지 않는다.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ActionSuggestion, AnalysisSnapshot, Hypothesis, NextSurveyQuestion, ProductFamily, Report, Round
from app.services.action_cards import CARD_AREA, parse_card_sentence, rank_notice
from app.services.evidence import evidence_counts
from app.services.question_forms import KIND_OPPORTUNITY, OPPORTUNITY_HYPOTHESIS_KIND, OPPORTUNITY_STATEMENT, normalize_question
from app.services.hypotheses import SMALL_SAMPLE_ROW_IDS


NOTE_SMALL_SAMPLE = "표본 적음 — 데이터 보강 필요(문항 없음)"
NOTE_NO_QUESTION = "문항 없음(검증을 통과한 문항이 없음)"


def latest_report(session: Session, family_id: int, round_id: int) -> Report | None:
    return session.scalars(
        select(Report)
        .where(Report.round_id == round_id, Report.family_id == family_id)
        .order_by(Report.generated_at.desc(), Report.report_id.desc())
    ).first()


def latest_draft_run_id(session: Session, report_id: int) -> int | None:
    return session.scalar(
        select(func.max(NextSurveyQuestion.run_id)).where(NextSurveyQuestion.report_id == report_id, NextSurveyQuestion.run_id.is_not(None))
    )


def report_snapshot_id(session: Session, report_id: int) -> int | None:
    return session.scalar(
        select(ActionSuggestion.snapshot_id).where(ActionSuggestion.report_id == report_id).order_by(ActionSuggestion.order_no)
    )


def counts_for_list(session: Session, report_ids: list[int]) -> dict[int, tuple[int, int]]:
    """report_id -> (제안 문장 수, 최신 초안의 문항 수)."""
    result = {}
    for report_id in report_ids:
        suggestions = session.scalar(select(func.count()).select_from(ActionSuggestion).where(ActionSuggestion.report_id == report_id))
        run_id = latest_draft_run_id(session, report_id)
        questions = (
            session.scalar(
                select(func.count()).select_from(NextSurveyQuestion).where(NextSurveyQuestion.report_id == report_id, NextSurveyQuestion.run_id == run_id)
            )
            if run_id is not None
            else 0
        )
        result[report_id] = (suggestions or 0, questions or 0)
    return result


def check_question_no(session: Session, report_id: int) -> int | None:
    """같은 리포트의 최신 문항 초안에서 영역 확인 문항(kind = opportunity_matrix)의 번호(order_no). 없으면 None."""
    run_id = latest_draft_run_id(session, report_id)
    if run_id is None:
        return None
    for question in session.scalars(
        select(NextSurveyQuestion).where(NextSurveyQuestion.report_id == report_id, NextSurveyQuestion.run_id == run_id).order_by(NextSurveyQuestion.order_no)
    ):
        if normalize_question(question.type, question.options_json)["kind"] == KIND_OPPORTUNITY:
            return question.order_no
    return None


def survey_respondents(snapshot: AnalysisSnapshot | None) -> int | None:
    """스냅샷 표의 설문 응답 수(survey:respondents). 없으면 None."""
    if snapshot is None:
        return None
    for row in snapshot.table_json.get("rows", []):
        if row.get("row_id") == "survey:respondents":
            return row.get("metrics", {}).get("응답자 수")
    return None


def card_fields(session: Session, report_id: int, suggestions: list, snapshots: dict) -> tuple[list[dict], str | None]:
    """문장마다 카드 필드(parse_card_sentence + check_question_no)와 리포트 단위 안내(rank_notice). 액션플랜 API와 리포트 API가 같이 쓴다."""
    check_no = check_question_no(session, report_id)
    extras, area_labels, respondents = [], [], None
    for suggestion in suggestions:
        parsed = parse_card_sentence(suggestion.sentence)
        is_area = parsed["card_kind"] == CARD_AREA
        parsed["check_question_no"] = check_no if is_area else None
        if is_area:
            area_labels.append(parsed["rank_label"])
            if respondents is None:
                respondents = survey_respondents(snapshots.get(suggestion.snapshot_id))
        extras.append(parsed)
    return extras, rank_notice(area_labels, respondents, check_no)


def build_report(session: Session, report_id: int) -> dict | None:
    """A-6 응답(과 내보내기 입력). 없으면 None."""
    report = session.get(Report, report_id)
    if report is None:
        return None
    round_row = session.get(Round, report.round_id)
    family = session.get(ProductFamily, report.family_id) if report.family_id is not None else None
    suggestions = session.scalars(
        select(ActionSuggestion).where(ActionSuggestion.report_id == report_id).order_by(ActionSuggestion.order_no)
    ).all()
    snapshots = {
        s.snapshot_id: s
        for s in session.scalars(select(AnalysisSnapshot).where(AnalysisSnapshot.snapshot_id.in_({x.snapshot_id for x in suggestions})))
    }
    plan = []
    card_extras, notice = card_fields(session, report_id, suggestions, snapshots)
    for suggestion, extra in zip(suggestions, card_extras):
        snapshot = snapshots[suggestion.snapshot_id]
        rows = {row["row_id"]: row for row in snapshot.table_json["rows"]}
        sources = sorted({rows[rid]["source"] for rid in suggestion.row_ids if rid in rows}, key=lambda s: (s != "합성", s))
        plan.append(
            {
                "suggestion_id": suggestion.suggestion_id,
                "order_no": suggestion.order_no,
                "sentence": suggestion.sentence,
                "evidence_count": evidence_counts(snapshot, suggestion.row_ids),
                "has_synthetic": "합성" in sources,
                "sources": sources,
                **extra,
            }
        )
    run_id = latest_draft_run_id(session, report_id)
    questions = []
    if run_id is not None:
        rows = session.execute(
            select(NextSurveyQuestion, Hypothesis)
            .outerjoin(Hypothesis, Hypothesis.hypothesis_id == NextSurveyQuestion.hypothesis_id)  # 영역 확인 문항은 가설이 없다
            .where(NextSurveyQuestion.report_id == report_id, NextSurveyQuestion.run_id == run_id)
            .order_by(NextSurveyQuestion.order_no)
        ).all()
        for question, hypothesis in rows:
            normalized = normalize_question(question.type, question.options_json)  # question-v3 이전(목록)과 question-v4(객체)를 같은 필드로 읽는다
            questions.append(
                {
                    "order_no": question.order_no,
                    "text": question.text,
                    "type": question.type,
                    "options": normalized["options"],
                    "form": normalized["form"],
                    "items": normalized["items"],
                    "low_label": normalized["low_label"],
                    "high_label": normalized["high_label"],
                    "kind": normalized["kind"],
                    "hypothesis_id": None if hypothesis is None else hypothesis.hypothesis_id,
                    "hypothesis_kind": OPPORTUNITY_HYPOTHESIS_KIND if hypothesis is None else hypothesis.kind,
                    "hypothesis_statement": OPPORTUNITY_STATEMENT if hypothesis is None else hypothesis.statement,
                }
            )
    # 같은 실행에서 저장됐지만 문항이 없는 가설. R1(표본 적음)은 호출 C 입력에서 빼므로 항상 여기에 나온다.
    no_question = []
    if run_id is not None:
        asked = {q["hypothesis_id"] for q in questions}
        for hypothesis in session.scalars(select(Hypothesis).where(Hypothesis.run_id == run_id).order_by(Hypothesis.hypothesis_id)):
            if hypothesis.hypothesis_id in asked:
                continue
            small_sample = hypothesis.related_row_ids == SMALL_SAMPLE_ROW_IDS
            no_question.append(
                {
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "kind": hypothesis.kind,
                    "statement": hypothesis.statement,
                    "note": NOTE_SMALL_SAMPLE if small_sample else NOTE_NO_QUESTION,
                }
            )
    return {
        "report_id": report.report_id,
        "round": {"round_id": round_row.round_id, "label": round_row.label},
        "family": None if family is None else {"family_id": family.family_id, "name": family.name},
        "generated_at": report.generated_at.isoformat(),
        "action_plan": plan,
        "rank_notice": notice,
        "next_survey": {"status": "draft", "run_id": run_id, "questions": questions, "no_question_hypotheses": no_question},
    }
