"""합성 설문 적재. 임시 SQLite만 쓴다."""

from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import Round, SurveyAnswer, SurveyQuestion, SurveyResponse
from app.services.survey_load import LoadError, load_synthetic_survey
from app.services.synthetic_survey import generate


def counts(session):
    return {
        "round": session.scalar(select(func.count()).select_from(Round)),
        "question": session.scalar(select(func.count()).select_from(SurveyQuestion)),
        "response": session.scalar(select(func.count()).select_from(SurveyResponse)),
        "answer": session.scalar(select(func.count()).select_from(SurveyAnswer)),
    }


def load(session, data):
    result = load_synthetic_survey(session, data)
    session.commit()
    return result


def count_where(session, model, condition):
    return session.scalar(select(func.count()).select_from(model).where(condition))


def test_first_load_creates_expected_rows(session):
    data = generate()
    result = load(session, data)
    assert result["survey_question"] == 20 and result["survey_response"] == 200
    state = counts(session)
    assert state["round"] == 2 and state["question"] == 20 and state["response"] == 200
    expected_answers = sum(len(v) for r in data["rounds"] for a in r["responses"] for v in a.values())
    assert state["answer"] == expected_answers
    assert count_where(session, SurveyResponse, SurveyResponse.is_synthetic.is_(False)) == 0
    assert count_where(session, SurveyResponse, SurveyResponse.family_id.is_not(None)) == 0
    rounds = {r.label: r for r in session.scalars(select(Round))}
    assert (rounds["2026-Q1"].period_start, rounds["2026-Q1"].period_end) == (date(2026, 1, 1), date(2026, 3, 31))
    assert (rounds["2026-Q2"].period_start, rounds["2026-Q2"].period_end) == (date(2026, 4, 1), date(2026, 6, 30))


def test_repeated_load_does_not_grow(session):
    data = generate()
    load(session, data)
    first = counts(session)
    for _ in range(3):
        load(session, data)
    assert counts(session) == first


def test_questions_keep_option_order_and_are_unique_per_round(session):
    load(session, generate())
    question = session.scalars(select(SurveyQuestion).where(SurveyQuestion.code == "q08")).first()
    assert [o["code"] for o in question.options_json] == ["1", "2", "3", "4", "5"]
    assert question.options_json[-1]["label"] == "개선할 점 없음" and question.type == "multi"
    assert count_where(session, SurveyQuestion, SurveyQuestion.code == "q01") == 2


def test_multi_answers_are_one_row_per_choice(session):
    load(session, generate())
    q8 = session.scalars(select(SurveyQuestion.question_id).where(SurveyQuestion.code == "q08")).all()
    rows = session.scalars(select(SurveyAnswer).where(SurveyAnswer.question_id.in_(q8))).all()
    per_response = {}
    for row in rows:
        per_response.setdefault(row.response_id, []).append(row.value)
    assert len(per_response) == 200
    assert all(("5" not in v) or v == ["5"] for v in per_response.values())


def test_pilot_round_and_non_synthetic_rows_are_never_touched(session):
    pilot = Round(label="[파일럿-임시] 2026-11-02")
    session.add(pilot)
    session.flush()
    real = SurveyResponse(round_id=pilot.round_id, family_id=None, is_synthetic=False)
    session.add(real)
    session.commit()
    load(session, generate())
    load(session, generate())
    assert session.get(Round, pilot.round_id).label.startswith("[파일럿-임시]")
    assert count_where(session, SurveyResponse, SurveyResponse.is_synthetic.is_(False)) == 1
    assert session.get(SurveyResponse, real.response_id) is not None


def test_load_aborts_when_a_non_synthetic_answer_still_references_a_question(session):
    load(session, generate())
    q1 = session.scalars(select(SurveyQuestion).where(SurveyQuestion.code == "q01")).first()
    real = SurveyResponse(round_id=q1.round_id, family_id=None, is_synthetic=False)
    session.add(real)
    session.flush()
    session.add(SurveyAnswer(response_id=real.response_id, question_id=q1.question_id, value="3"))
    session.commit()
    before = counts(session)
    with pytest.raises(LoadError):
        load_synthetic_survey(session, generate())
    session.rollback()
    assert counts(session) == before


def test_load_rolls_back_on_invalid_data(session):
    data = generate()
    data["rounds"][1]["responses"][3]["q01"] = ["9"]
    with pytest.raises(ValueError):
        load_synthetic_survey(session, data)
    session.rollback()
    assert counts(session) == {"round": 0, "question": 0, "response": 0, "answer": 0}


def test_temp_round_label_is_refused(session):
    data = generate()
    data["rounds"][0]["label"] = "[파일럿-임시] x"
    with pytest.raises(ValueError):
        load_synthetic_survey(session, data)
