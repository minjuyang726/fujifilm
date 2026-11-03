"""액션플랜 조회: GET /api/families/{family_id}/action-plan?round_id= (구현에서 정함, spec.md A-6 대신 Phase 5용 가장 단순한 형태).

제품군 x 회차의 가장 최근 성공한 리포트(action-suggestions 실행)의 문장 목록을 돌려준다. 읽기 전용이다.
문장마다 근거 건수(리뷰, 설문)만 담고 근거 목록은 A-10으로 조회한다(SP-3). 아직 결과가 없으면 report가 null이고 목록은 비어 있다.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ActionSuggestion, AnalysisSnapshot, ProductFamily, Report, Round
from app.routers.read import TEMP_ROUND_PREFIX
from app.schemas.dashboard import DashboardFamily, DashboardRound
from app.services.evidence import evidence_counts
from app.services.report_data import card_fields

router = APIRouter(prefix="/api", tags=["plan"])


class EvidenceCount(BaseModel):
    review: int
    survey: int


class PlanSentence(BaseModel):
    suggestion_id: int
    order_no: int
    sentence: str
    evidence_count: EvidenceCount
    has_synthetic: bool  # 설문(합성) 행을 근거로 하는 문장이면 참. 화면이 "합성" 배지를 붙인다(FR-1.10)
    card_kind: str  # area | voc | legacy (sentence를 쪼갠 카드 필드, 이전 형식은 legacy)
    area_label: str | None
    rank_label: str | None
    priority_text: str
    deliverable_kind: str | None
    deliverable_text: str | None
    check_question_no: int | None


class ReportInfo(BaseModel):
    report_id: int
    run_id: int
    snapshot_id: int | None
    generated_at: str


class ActionPlanResponse(BaseModel):
    family: DashboardFamily
    round: DashboardRound
    report: ReportInfo | None
    action_plan: list[PlanSentence]
    rank_notice: str | None = None


@router.get("/families/{family_id}/action-plan", response_model=ActionPlanResponse)
def get_action_plan(family_id: int, round_id: int, session: Session = Depends(get_session)) -> dict:
    family = session.get(ProductFamily, family_id)
    if family is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "제품군을 찾을 수 없습니다."})
    round_row = session.get(Round, round_id)
    if round_row is None or round_row.label.startswith(TEMP_ROUND_PREFIX):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "회차를 찾을 수 없습니다."})
    base = {
        "family": {"family_id": family.family_id, "name": family.name},
        "round": {"round_id": round_row.round_id, "label": round_row.label},
    }
    # 리포트는 성공한 실행에서만 만들어진다. 가장 최근(report_id가 큰 쪽)을 보여준다.
    report = session.scalars(
        select(Report)
        .where(Report.round_id == round_id, Report.family_id == family_id)
        .order_by(Report.generated_at.desc(), Report.report_id.desc())
    ).first()
    if report is None:
        return {**base, "report": None, "action_plan": [], "rank_notice": None}
    suggestions = session.scalars(
        select(ActionSuggestion).where(ActionSuggestion.report_id == report.report_id).order_by(ActionSuggestion.order_no)
    ).all()
    snapshots = {s.snapshot_id: s for s in session.scalars(select(AnalysisSnapshot).where(AnalysisSnapshot.snapshot_id.in_({x.snapshot_id for x in suggestions})))}
    plan = []
    card_extras, notice = card_fields(session, report.report_id, suggestions, snapshots)
    for suggestion, extra in zip(suggestions, card_extras):
        snapshot = snapshots[suggestion.snapshot_id]
        rows = {row["row_id"]: row for row in snapshot.table_json["rows"]}
        plan.append(
            {
                "suggestion_id": suggestion.suggestion_id,
                "order_no": suggestion.order_no,
                "sentence": suggestion.sentence,
                "evidence_count": evidence_counts(snapshot, suggestion.row_ids),
                "has_synthetic": any(rows.get(row_id, {}).get("source") == "합성" for row_id in suggestion.row_ids),
                **extra,
            }
        )
    return {
        **base,
        "report": {
            "report_id": report.report_id,
            "run_id": report.run_id,
            "snapshot_id": suggestions[0].snapshot_id if suggestions else None,
            "generated_at": report.generated_at.isoformat(),
        },
        "action_plan": plan,
        "rank_notice": notice,
    }
