"""step next-survey-draft와 report-assembly 전체 흐름(가짜 클라이언트). 실제 OpenAI는 호출하지 않고 모든 값은 가짜다."""

import json

import pytest
from sqlalchemy import select

from app.llm.client import LLMResult, PermanentLLMError, TransientLLMError
from app.llm.cost import CostGuard, Prices
from app.main import app
from app.models import Hypothesis, LlmCallLog, NextSurveyQuestion, PipelineRun, ProductFamily, Report
from app.routers.pipeline import get_llm_client_factory
from app.routers.steps import get_question_model_provider
from app.services import question_step
from app.services.question_step import run_next_survey_draft, snapshot_for_report
from app.services.report_data import latest_report
from tests.fakes import ScriptedClient
from tests.test_suggestion_step import good_sentences, llm_text, set_llm, snapshot_via_api, world  # noqa: F401


class QuestionClient:
    """프롬프트의 가설마다 문항 하나를 돌려주는 가짜 클라이언트. omit에 든 번호(0부터)의 가설은 빼고 답한다."""

    def __init__(self, omit=(), mutate=None, tokens=(800, 300)):
        self.calls = []
        self.omit = set(omit)
        self.mutate = mutate
        self.tokens = tokens

    def complete_json(self, *, model, system_prompt, user_prompt, schema_name, json_schema):
        self.calls.append({"model": model, "system_prompt": system_prompt, "user_prompt": user_prompt, "schema_name": schema_name})
        hypotheses = json.loads(user_prompt.split("\n", 1)[1])
        questions = []
        for index, item in enumerate(hypotheses):
            if index in self.omit:
                continue
            kind = ["scale5", "single", "multi"][index % 3]
            questions.append(
                {
                    "hypothesis_id": item["hypothesis_id"],
                    "text": f"가설 {chr(65 + index)}에 대해 어떻게 생각하시나요?".replace("가설 A", "첫째 가설").replace("가설 B", "둘째 가설"),
                    "type": kind,
                    "options": None if kind == "scale5" else ["선택지 가", "선택지 나", "선택지 다"],
                }
            )
        if self.mutate:
            questions = self.mutate(questions)
        return LLMResult(text=json.dumps({"questions": questions}, ensure_ascii=False), input_tokens=self.tokens[0], output_tokens=self.tokens[1])


def use_client(client, model="fake-question-model"):
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda: client)
    app.dependency_overrides[get_question_model_provider] = lambda: (lambda: model)
    return client


def make_report(world):
    """스냅샷 -> action-suggestions(가짜) 까지 만들어 report를 준비한다."""
    snapshot = snapshot_via_api(world)
    set_llm([llm_text(*good_sentences(snapshot))])
    response = world.post(f"/api/rounds/{world.q1.round_id}/pipeline/action-suggestions", json={"family_id": 1})
    assert response.status_code == 201 and response.json()["status"] == "succeeded"
    return latest_report(world.session, 1, world.q1.round_id)


def run_draft(world, family_id=1):
    return world.post(f"/api/rounds/{world.q1.round_id}/pipeline/next-survey-draft", json={"family_id": family_id})


def test_full_flow_saves_hypotheses_and_draft_questions(world):
    report = make_report(world)
    client = use_client(QuestionClient())
    response = run_draft(world)
    assert response.status_code == 201
    body = response.json()
    assert body["step"] == "next-survey-draft" and body["status"] == "succeeded"
    run = world.session.get(PipelineRun, body["run_id"])
    hypotheses = world.session.scalars(select(Hypothesis).order_by(Hypothesis.hypothesis_id)).all()
    questions = world.session.scalars(select(NextSurveyQuestion).order_by(NextSurveyQuestion.order_no)).all()
    assert hypotheses and len(hypotheses) <= 5
    assert all(h.run_id == run.run_id and h.round_id == world.q1.round_id and h.family_id == 1 for h in hypotheses)
    assert {h.snapshot_id for h in hypotheses} == {snapshot_for_report(world.session, report).snapshot_id}
    # 가설당 문항 1개, 모두 draft, 모두 가설과 연결, 순서는 가설 우선순위 순서
    assert len(questions) == len(hypotheses)
    assert all(q.status == "draft" and q.report_id == report.report_id and q.run_id == run.run_id for q in questions)
    assert [q.hypothesis_id for q in questions] == [h.hypothesis_id for h in hypotheses]
    assert [q.order_no for q in questions] == list(range(1, len(questions) + 1))
    by_type = {q.type: q for q in questions}
    assert [o["code"] for o in by_type["scale5"].options_json] == ["1", "2", "3", "4", "5"] and by_type["scale5"].options_json[0]["label"] == "1점"
    assert [o["label"] for o in by_type["single"].options_json] == ["선택지 가", "선택지 나", "선택지 다"]
    assert run.counters["hypotheses"] == len(hypotheses) and run.counters["accepted"] == len(questions)
    assert run.counters["rules"].get("R3") == 1 and run.counters["attempts"] == 1 and run.counters["llm_calls"] == 1
    assert run.counters["dropped_reasons"] == {} and run.error_code is None
    log = world.session.scalars(select(LlmCallLog).where(LlmCallLog.run_id == run.run_id)).all()
    assert len(log) == 1 and log[0].call_type == "C" and log[0].prompt_version == "question-v1" and log[0].model_name == "fake-question-model"
    # 호출 C에는 가설의 id·종류·진술문만 간다
    sent = client.calls[0]["user_prompt"]
    for forbidden in ("related_row_ids", "survey:q", "review_text", "author", "allowed_evidence"):
        assert forbidden not in sent
    assert json.loads(sent.split("\n", 1)[1])[0].keys() == {"hypothesis_id", "kind", "statement"}


def test_step_not_ready_without_report_or_snapshot(world):
    use_client(QuestionClient())
    assert run_draft(world).json()["error"]["code"] == "STEP_NOT_READY"
    snapshot_via_api(world)  # 스냅샷만 있고 리포트가 없다
    assert run_draft(world).json()["error"]["code"] == "STEP_NOT_READY"
    assert world.session.scalars(select(PipelineRun).where(PipelineRun.step == "next-survey-draft")).all() == []


def test_zero_hypotheses_fail_without_calling_the_llm(world, monkeypatch):
    make_report(world)
    client = use_client(QuestionClient())
    monkeypatch.setattr(question_step, "hypotheses_for", lambda session, snapshot: [])
    monkeypatch.setattr("app.routers.steps.hypotheses_for", lambda session, snapshot: [])
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "failed" and run.error_code == "NO_HYPOTHESES" and run.counters["hypotheses"] == 0
    assert client.calls == [] and world.session.scalars(select(Hypothesis)).all() == []
    assert world.session.scalars(select(NextSurveyQuestion)).all() == []


def test_invalid_questions_are_dropped_by_category(world):
    make_report(world)

    def mutate(questions):
        questions[0]["text"] = "월 3회 이상 쓰시나요?"  # 숫자
        questions[1]["options"] = ["하나"]  # 선택지 개수
        questions.append({**questions[2], "text": "같은 가설에 둘째 문항인가요?"})  # 같은 가설 둘째 문항
        questions.append({"hypothesis_id": 999999, "text": "없는 가설인가요?", "type": "single", "options": ["가", "나"]})
        return questions

    use_client(QuestionClient(mutate=mutate))
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "succeeded"
    c = run.counters
    assert c["dropped_number"] == 1 and c["dropped_hypothesis"] == 2 and c["dropped_format"] == 1
    assert c["dropped_reasons"] == {"has_number": 1, "bad_options": 1, "duplicate_hypothesis": 1, "unknown_hypothesis": 1}
    assert c["accepted"] == c["hypotheses"] - 2 and c["proposed"] == c["hypotheses"] + 2
    # 문항 내용은 실행 기록에 없다
    assert "월 3회" not in json.dumps(c, ensure_ascii=False)


def test_zero_accepted_questions_fail_after_three_requests(world):
    make_report(world)
    client = use_client(QuestionClient(mutate=lambda qs: [{**q, "text": "3점 이상인가요?"} for q in qs]))
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "failed" and run.error_code == "NO_QUESTIONS"
    assert run.counters["attempts"] == 3 and run.counters["llm_calls"] == 3 == len(client.calls)
    assert world.session.scalars(select(NextSurveyQuestion)).all() == []
    assert [l.status for l in world.session.scalars(select(LlmCallLog).where(LlmCallLog.run_id == run.run_id))] == ["invalid_output"] * 3
    assert world.session.scalars(select(Hypothesis)).all()  # 가설은 저장된다(쌓는다)


def test_broken_json_then_valid_output_succeeds_on_the_second_request(world):
    make_report(world)
    good = QuestionClient()
    script = [LLMResult(text="not json", input_tokens=10, output_tokens=5)]

    class Mixed:
        calls = []

        def complete_json(self, **kwargs):
            self.calls.append(kwargs)
            return script.pop(0) if script else good.complete_json(**kwargs)

    use_client(Mixed())
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "succeeded" and run.counters["attempts"] == 2 and run.counters["llm_calls"] == 2


def test_reruns_stack_and_questions_keep_their_run_id(world):
    report = make_report(world)
    use_client(QuestionClient())
    first, second = run_draft(world).json(), run_draft(world).json()
    assert first["run_id"] != second["run_id"]
    rows = world.session.scalars(select(NextSurveyQuestion).where(NextSurveyQuestion.report_id == report.report_id)).all()
    assert {r.run_id for r in rows} == {first["run_id"], second["run_id"]}
    assert len(world.session.scalars(select(Report)).all()) == 1  # 리포트는 늘지 않는다


def test_config_errors_and_cost_limit_do_not_create_runs(world, monkeypatch):
    make_report(world)
    app.dependency_overrides.pop(get_question_model_provider, None)
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda: QuestionClient())
    assert run_draft(world).json()["error"]["code"] == "MODEL_NOT_CONFIGURED"  # OPENAI_MODEL_QUESTION 없음
    use_client(QuestionClient())
    monkeypatch.delenv("OPENAI_PRICE_OUTPUT_PER_M")
    assert run_draft(world).json()["error"]["code"] == "PRICE_NOT_CONFIGURED"
    monkeypatch.setenv("OPENAI_PRICE_OUTPUT_PER_M", "1.20")
    monkeypatch.setenv("QUESTION_COST_LIMIT_USD", "0.000001")
    response = run_draft(world)
    assert response.status_code == 422 and response.json()["error"]["code"] == "COST_LIMIT_EXCEEDED"
    assert world.session.scalars(select(PipelineRun).where(PipelineRun.step == "next-survey-draft")).all() == []


def test_request_validation(world):
    use_client(QuestionClient())
    q1 = world.q1.round_id
    assert world.post(f"/api/rounds/{q1}/pipeline/next-survey-draft", json={}).status_code == 422
    assert world.post(f"/api/rounds/{q1}/pipeline/next-survey-draft", json={"family_id": 99}).status_code == 404
    assert world.post("/api/rounds/999/pipeline/next-survey-draft", json={"family_id": 1}).status_code == 404


# ---------- 서비스 직접 호출: 재시도, 비용 가드, 내부 오류 ----------
def service_call(world, client, **kwargs):
    report = make_report(world)
    sleeps = []
    run = run_next_survey_draft(
        world.session, round_row=world.q1, family=world.session.get(ProductFamily, 1), report=report,
        snapshot=snapshot_for_report(world.session, report), client=client, model_name="fake-question-model",
        sleep=sleeps.append, **kwargs,
    )
    return run, sleeps


def test_transient_errors_are_retried_with_growing_waits(world):
    good = QuestionClient()
    script = [TransientLLMError("TIMEOUT"), TransientLLMError("RATE_LIMIT")]

    class Flaky:
        def complete_json(self, **kwargs):
            if script:
                raise script.pop(0)
            return good.complete_json(**kwargs)

    run, sleeps = service_call(world, Flaky())
    assert run.status == "succeeded" and sleeps == [1, 2] and run.counters["llm_calls"] == 3 and run.counters["attempts"] == 1
    logs = world.session.scalars(select(LlmCallLog).where(LlmCallLog.run_id == run.run_id).order_by(LlmCallLog.call_id)).all()
    assert [(l.status, l.error_code) for l in logs] == [("api_error", "TIMEOUT"), ("api_error", "RATE_LIMIT"), ("ok", None)]


def test_transient_errors_exhaust_and_permanent_errors_stop(world):
    run, sleeps = service_call(world, ScriptedClient([TransientLLMError("TIMEOUT")] * 4))
    assert run.status == "failed" and run.error_code == "TIMEOUT" and sleeps == [1, 2, 4] and run.counters["llm_calls"] == 4


def test_permanent_error_is_not_retried(world):
    client = ScriptedClient([PermanentLLMError("HTTP_401")])
    run, sleeps = service_call(world, client)
    assert run.status == "failed" and run.error_code == "HTTP_401" and sleeps == [] and len(client.calls) == 1


def test_cost_guard_stops_retries_when_exceeded(world):
    bad = LLMResult(text="not json", input_tokens=1_000_000, output_tokens=0)
    client = ScriptedClient([bad, bad, bad])
    run, _ = service_call(world, client, cost_guard=CostGuard(0.01, Prices(0.20, 1.20)))
    assert run.status == "failed" and run.error_code == "COST_LIMIT" and len(client.calls) == 1


def test_internal_error_marks_the_run_failed_without_details(world):
    class Boom:
        def complete_json(self, **kwargs):
            raise RuntimeError("비밀 접속 문자열 postgresql://u:p@h/db")

    run, _ = service_call(world, Boom())
    assert run.status == "failed" and run.error_code == "INTERNAL_ERROR" and "postgresql" not in json.dumps(run.counters)


# ---------- report-assembly ----------
def test_report_assembly_checks_both_parts_and_only_records_a_run(world):
    make_report(world)
    url = f"/api/rounds/{world.q1.round_id}/pipeline/report-assembly"
    not_ready = world.post(url, json={"family_id": 1})
    assert not_ready.status_code == 400 and not_ready.json()["error"]["code"] == "STEP_NOT_READY"  # 초안이 아직 없다
    use_client(QuestionClient())
    run_draft(world)
    before = (len(world.session.scalars(select(Report)).all()), len(world.session.scalars(select(NextSurveyQuestion)).all()))
    response = world.post(url, json={"family_id": 1})
    assert response.status_code == 201 and response.json()["step"] == "report-assembly" and response.json()["status"] == "succeeded"
    run = world.session.get(PipelineRun, response.json()["run_id"])
    assert run.counters["suggestions"] == 2 and run.counters["questions"] >= 1 and run.counters["report_id"]
    after = (len(world.session.scalars(select(Report)).all()), len(world.session.scalars(select(NextSurveyQuestion)).all()))
    assert before == after  # 새 데이터를 만들지 않는다


def test_report_assembly_without_any_report_is_not_ready(world):
    assert world.post(f"/api/rounds/{world.q1.round_id}/pipeline/report-assembly", json={"family_id": 1}).status_code == 400
    assert world.post(f"/api/rounds/{world.q1.round_id}/pipeline/report-assembly", json={"family_id": 99}).status_code == 404
