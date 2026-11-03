"""리포트 조회·조립용 읽기 함수(A-5, A-6, A-7, report-assembly). 읽기 전용이다.

- 최신 리포트 = 제품군 x 회차에서 성공한 action-suggestions로 만들어진 가장 최근 report(report는 성공한 실행에서만 만든다).
- 최신 초안 = 해당 report의 next_survey_question 중 가장 큰 run_id의 것(결정 2026-11-03). 초안이 없으면 문항 목록이 비어 있다.
- 리뷰 본문과 작성자는 읽지 않는다.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ActionSuggestion, AnalysisSnapshot, Hypothesis, NextSurveyQuestion, ProductFamily, Report, Round
from app.services.evidence import evidence_counts
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
    for suggestion in suggestions:
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
            }
        )
    run_id = latest_draft_run_id(session, report_id)
    questions = []
    if run_id is not None:
        rows = session.execute(
            select(NextSurveyQuestion, Hypothesis)
            .join(Hypothesis, Hypothesis.hypothesis_id == NextSurveyQuestion.hypothesis_id)
            .where(NextSurveyQuestion.report_id == report_id, NextSurveyQuestion.run_id == run_id)
            .order_by(NextSurveyQuestion.order_no)
        ).all()
        for question, hypothesis in rows:
            questions.append(
                {
                    "order_no": question.order_no,
                    "text": question.text,
                    "type": question.type,
                    "options": question.options_json,
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "hypothesis_kind": hypothesis.kind,
                    "hypothesis_statement": hypothesis.statement,
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
        "next_survey": {"status": "draft", "run_id": run_id, "questions": questions, "no_question_hypotheses": no_question},
    }
