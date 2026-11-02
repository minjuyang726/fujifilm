"""대시보드(A-3)의 설문 집계. 계산은 코드가 한다(FR-0.1). 읽기 전용이다.

- 설문 집계는 항상 비가중이다(FR-1.9). 가중치가 없고 응답 한 건은 한 번 센다.
- ratio = 선택 수 / respondent_count (소수 4자리 반올림). 다중선택은 합이 1을 넘을 수 있다.
- 선택 수가 0인 선택지도 options_json 순서대로 포함하고, 문항은 question_id 순이다.
"""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import SurveyAnswer, SurveyQuestion, SurveyResponse

RATIO_DIGITS = 4
SYNTHETIC_LABEL = "합성"


def survey_section(session: Session, round_id: int) -> dict:
    respondent_count, synthetic_count = session.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((SurveyResponse.is_synthetic.is_(True), 1), else_=0)), 0),
        ).where(SurveyResponse.round_id == round_id)
    ).one()
    # 응답이 있고 모두 합성이면 "합성", 아니면(합성이 아닌 응답이 섞였거나 응답이 없으면) null
    label = SYNTHETIC_LABEL if respondent_count > 0 and synthetic_count == respondent_count else None

    counts: dict[tuple[int, str], int] = {
        (question_id, value): n
        for question_id, value, n in session.execute(
            select(SurveyAnswer.question_id, SurveyAnswer.value, func.count())
            .join(SurveyQuestion, SurveyQuestion.question_id == SurveyAnswer.question_id)
            .where(SurveyQuestion.round_id == round_id)
            .group_by(SurveyAnswer.question_id, SurveyAnswer.value)
        )
    }
    questions = session.scalars(
        select(SurveyQuestion).where(SurveyQuestion.round_id == round_id).order_by(SurveyQuestion.question_id)
    ).all()

    items = []
    for question in questions:
        results = []
        for option in question.options_json:
            count = counts.get((question.question_id, option["code"]), 0)
            ratio = round(count / respondent_count, RATIO_DIGITS) if respondent_count else 0.0
            results.append({"code": option["code"], "option": option["label"], "count": count, "ratio": ratio})
        items.append({"question_id": question.question_id, "text": question.text, "type": question.type, "results": results})
    return {"respondent_count": respondent_count, "synthetic_label": label, "scope": "common", "questions": items}
