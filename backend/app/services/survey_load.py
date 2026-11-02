"""합성 설문 데이터를 DB에 적재한다. 여러 번 실행해도 행이 늘지 않는다.

순서(FK 때문에 자식부터 지운다): 회차 upsert -> survey_answer 삭제 -> survey_response 삭제
-> survey_question 삭제(남은 참조가 있으면 중단) -> 다시 삽입.
is_synthetic이 거짓인 응답과 label이 '[파일럿-임시]'로 시작하는 회차는 건드리지 않는다.
"""

from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Round, SurveyAnswer, SurveyQuestion, SurveyResponse
from app.services.synthetic_survey import validate_dataset

TEMP_ROUND_PREFIX = "[파일럿-임시]"


class LoadError(RuntimeError):
    """적재를 중단해야 할 때. 메시지에는 건수와 회차 label만 쓴다."""


def load_synthetic_survey(session: Session, data: dict) -> dict:
    """한 트랜잭션으로 적재하고 건수를 돌려준다. 호출한 쪽이 commit한다(오류가 나면 호출한 쪽이 rollback)."""
    validate_dataset(data)
    counts = {"round": 0, "survey_question": 0, "survey_response": 0, "survey_answer": 0}

    for round_data in data["rounds"]:
        label = round_data["label"]
        if label.startswith(TEMP_ROUND_PREFIX):
            raise LoadError("임시 회차는 적재 대상이 아닙니다")
        start = date.fromisoformat(round_data["period_start"])
        end = date.fromisoformat(round_data["period_end"])

        rounds = session.scalars(select(Round).where(Round.label == label)).all()
        if len(rounds) > 1:
            raise LoadError(f"{label}: 같은 label의 회차가 {len(rounds)}개입니다")
        if rounds:
            round_row = rounds[0]
            round_row.period_start, round_row.period_end = start, end
        else:
            round_row = Round(label=label, period_start=start, period_end=end)
            session.add(round_row)
        session.flush()
        round_id = round_row.round_id

        # 합성 응답의 답 -> 합성 응답. 합성이 아닌 응답은 지우지 않는다.
        synthetic_ids = select(SurveyResponse.response_id).where(
            SurveyResponse.round_id == round_id, SurveyResponse.is_synthetic.is_(True)
        )
        session.execute(delete(SurveyAnswer).where(SurveyAnswer.response_id.in_(synthetic_ids)))
        session.execute(
            delete(SurveyResponse).where(SurveyResponse.round_id == round_id, SurveyResponse.is_synthetic.is_(True))
        )

        # 문항: 이 회차 문항을 가리키는 답이 하나라도 남아 있으면 중단한다.
        question_ids = select(SurveyQuestion.question_id).where(SurveyQuestion.round_id == round_id)
        remaining = session.scalar(
            select(func.count()).select_from(SurveyAnswer).where(SurveyAnswer.question_id.in_(question_ids))
        )
        if remaining:
            raise LoadError(f"{label}: 합성이 아닌 답 {remaining}건이 문항을 참조하고 있어 중단합니다")
        session.execute(delete(SurveyQuestion).where(SurveyQuestion.round_id == round_id))
        session.flush()

        question_by_code = {}
        for question in round_data["questions"]:
            row = SurveyQuestion(
                round_id=round_id,
                code=question["code"],
                text=question["text"],
                type=question["type"],
                options_json=question["options"],
            )
            session.add(row)
            question_by_code[question["code"]] = row
        session.flush()

        responses = [SurveyResponse(round_id=round_id, family_id=None, is_synthetic=True) for _ in round_data["responses"]]
        session.add_all(responses)
        session.flush()
        answers = [
            SurveyAnswer(response_id=response.response_id, question_id=question_by_code[code].question_id, value=value)
            for response, answer_map in zip(responses, round_data["responses"])
            for code, values in answer_map.items()
            for value in values
        ]
        session.add_all(answers)
        session.flush()

        counts["round"] += 1
        counts["survey_question"] += len(question_by_code)
        counts["survey_response"] += len(responses)
        counts["survey_answer"] += len(answers)
    return counts
