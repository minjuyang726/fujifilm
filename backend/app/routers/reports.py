"""A-5(리포트 목록), A-6(리포트 조회), A-7(HTML 내보내기). 모두 읽기 전용이다.

A-5는 항목에 suggestion_count, question_count를 더했고, A-6은 문항에 가설 정보를 더했다(spec.md "구현에서 정함 (Phase 6)").
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Report
from app.services.report_data import build_report, counts_for_list
from app.services.report_export import render_report_html

router = APIRouter(prefix="/api", tags=["reports"])


class ReportListItem(BaseModel):
    report_id: int
    round_id: int
    family_id: int | None
    generated_at: str
    suggestion_count: int
    question_count: int


class ReportList(BaseModel):
    reports: list[ReportListItem]


class RoundOut(BaseModel):
    round_id: int
    label: str


class FamilyOut(BaseModel):
    family_id: int
    name: str


class EvidenceCountOut(BaseModel):
    review: int
    survey: int


class ActionPlanItem(BaseModel):
    suggestion_id: int
    order_no: int
    sentence: str
    evidence_count: EvidenceCountOut
    has_synthetic: bool
    sources: list[str]


class OptionOut(BaseModel):
    code: str
    label: str


class QuestionOut(BaseModel):
    order_no: int
    text: str
    type: str
    options: list[OptionOut] | None
    hypothesis_id: int
    hypothesis_kind: str
    hypothesis_statement: str


class NextSurvey(BaseModel):
    status: str
    run_id: int | None
    questions: list[QuestionOut]


class ReportOut(BaseModel):
    report_id: int
    round: RoundOut
    family: FamilyOut | None
    generated_at: str
    action_plan: list[ActionPlanItem]
    next_survey: NextSurvey


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "리포트를 찾을 수 없습니다."})


@router.get("/reports", response_model=ReportList)
def list_reports(round_id: int | None = None, family_id: int | None = None, session: Session = Depends(get_session)) -> dict:
    statement = select(Report).order_by(Report.report_id.desc())
    if round_id is not None:
        statement = statement.where(Report.round_id == round_id)
    if family_id is not None:
        statement = statement.where(Report.family_id == family_id)
    reports = session.scalars(statement).all()
    counts = counts_for_list(session, [r.report_id for r in reports])
    return {
        "reports": [
            {
                "report_id": r.report_id,
                "round_id": r.round_id,
                "family_id": r.family_id,
                "generated_at": r.generated_at.isoformat(),
                "suggestion_count": counts[r.report_id][0],
                "question_count": counts[r.report_id][1],
            }
            for r in reports
        ]
    }


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int, session: Session = Depends(get_session)) -> dict:
    report = build_report(session, report_id)
    if report is None:
        raise _not_found()
    return report


@router.get("/reports/{report_id}/export")
def export_report(report_id: int, format: str = Query(...), session: Session = Depends(get_session)) -> Response:
    if format != "html":
        raise HTTPException(status_code=400, detail={"code": "UNSUPPORTED_FORMAT", "message": "지원하지 않는 내보내기 형식입니다. format=html만 쓸 수 있습니다."})
    report = build_report(session, report_id)
    if report is None:
        raise _not_found()
    document = render_report_html(report)  # 외부 참조가 있으면 예외 -> 500 INTERNAL_ERROR
    return Response(
        content=document,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.html"'},
    )
