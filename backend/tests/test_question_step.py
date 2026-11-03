"""step next-survey-draft(question-v4)와 report-assembly 전체 흐름(가짜 클라이언트). 실제 OpenAI는 호출하지 않고 모든 값은 가짜다."""

import json

import pytest
from sqlalchemy import select

from app.llm.client import LLMResult, PermanentLLMError, TransientLLMError
from app.llm.cost import CostGuard, Prices
from app.main import app
from app.models import ActionSuggestion, Hypothesis, LlmCallLog, NextSurveyQuestion, PipelineRun, ProductFamily, Report, Round
from app.routers.pipeline import get_llm_client_factory
from app.routers.steps import get_question_model_provider
from app.services import question_step
from app.services.question_step import run_next_survey_draft, snapshot_for_report
from app.services.report_data import latest_report
from tests.fakes import ScriptedClient
from tests.test_suggestion_step import good_response, llm_text, set_llm, snapshot_via_api, world  # noqa: F401


class QuestionClient:
    """프롬프트의 가설마다 문구(text, low_label, high_label)를 돌려주는 가짜 클라이언트. omit에 든 번호(0부터)의 가설은 빼고 답한다."""

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
            questions.append(
                {
                    "hypothesis_id": item["hypothesis_id"],
                    "text": f"{chr(65 + index)} 주제에 대해 어떻게 생각하시나요?",
                    "low_label": "전혀 그렇지 않음",
                    "high_label": "매우 그러함",
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
    set_llm([good_response(world, snapshot)])
    response = world.post(f"/api/rounds/{world.q1.round_id}/pipeline/action-suggestions", json={"family_id": 1})
    assert response.status_code == 201 and response.json()["status"] == "succeeded"
    return latest_report(world.session, 1, world.q1.round_id)


def run_draft(world, family_id=1):
    return world.post(f"/api/rounds/{world.q1.round_id}/pipeline/next-survey-draft", json={"family_id": family_id})


def drafts(world):
    """저장된 문항을 order_no 순서로: (영역 확인 문항, 가설 문항들)."""
    rows = world.session.scalars(select(NextSurveyQuestion).order_by(NextSurveyQuestion.order_no)).all()
    return rows[0], rows[1:]


def test_full_flow_saves_hypotheses_and_draft_questions(world):
    report = make_report(world)
    client = use_client(QuestionClient())
    response = run_draft(world)
    assert response.status_code == 201
    body = response.json()
    assert body["step"] == "next-survey-draft" and body["status"] == "succeeded"
    run = world.session.get(PipelineRun, body["run_id"])
    hypotheses = world.session.scalars(select(Hypothesis).order_by(Hypothesis.hypothesis_id)).all()
    opportunity, questions = drafts(world)
    assert hypotheses and len(hypotheses) <= 5
    assert all(h.run_id == run.run_id and h.round_id == world.q1.round_id and h.family_id == 1 for h in hypotheses)
    assert {h.snapshot_id for h in hypotheses} == {snapshot_for_report(world.session, report).snapshot_id}
    # 같은 원문항에서 나온 가설은 한 문항이다: R3(q01×q09)와 R2(q09)가 q09 문항 하나로 합쳐진다. 저장 순서: R3, R2(q10), R2(q09), R2(q06), R1
    targets = [h for h in hypotheses if h.related_row_ids != ["voc:judged:count"]]  # R1(표본 적음)은 저장만 하고 문항을 만들지 않는다
    r3, r2_q10, r2_q09, r2_q06 = targets
    assert len(targets) == len(hypotheses) - 1 == 4 and len(questions) == 3
    assert all(q.status == "draft" and q.report_id == report.report_id and q.run_id == run.run_id for q in [opportunity, *questions])
    assert [q.hypothesis_id for q in questions] == [r3.hypothesis_id, r2_q10.hypothesis_id, r2_q06.hypothesis_id]  # 합쳐진 문항은 대표 가설(R3)에 연결된다
    assert questions[0].options_json["merged_hypothesis_ids"] == [r2_q09.hypothesis_id] and "merged_hypothesis_ids" not in questions[1].options_json
    assert [q.order_no for q in [opportunity, *questions]] == list(range(1, len(questions) + 2))
    # 형식과 항목은 코드가 정한다: q09 문항(R3+R2)은 scale10, q10 문항은 scale10, q06 문항은 항목이 있는 scale10_matrix
    assert [q.type for q in questions] == ["scale10", "scale10", "scale10_matrix"]
    assert all(q.options_json["kind"] == "hypothesis" and q.options_json["low_label"] == "전혀 그렇지 않음" and q.options_json["high_label"] == "매우 그러함" for q in questions)
    assert [item["label"] for item in questions[2].options_json["items"]] == ["여행", "모임·행사", "선물", "일상 기록"]  # q06의 기타(5)는 뺀다
    assert questions[0].options_json["items"] == []
    assert run.counters["hypotheses"] == len(hypotheses) and run.counters["accepted"] == len(questions) == 3
    assert run.counters["question_hypotheses"] == 3 and run.counters["merged_hypotheses"] == 1
    assert run.counters["rules"].get("R3") == 1 and run.counters["attempts"] == 1 and run.counters["llm_calls"] == 1 and run.counters["opportunity_question"] == 1
    assert run.counters["dropped_reasons"] == {} and run.error_code is None
    log = world.session.scalars(select(LlmCallLog).where(LlmCallLog.run_id == run.run_id)).all()
    assert len(log) == 1 and log[0].call_type == "C" and log[0].prompt_version == "question-v4" and log[0].model_name == "fake-question-model"
    # 호출 C에는 가설의 id·종류·형식·진술문만 간다: 항목 이름과 근거는 가지 않는다
    sent = client.calls[0]["user_prompt"]
    for forbidden in ("related_row_ids", "survey:q", "review_text", "author", "allowed_evidence", "items", "기타"):
        assert forbidden not in sent
    assert json.loads(sent.split("\n", 1)[1])[0].keys() == {"hypothesis_id", "kind", "form", "statement"}
    inputs = json.loads(sent.split("\n", 1)[1])
    assert [x["form"] for x in inputs] == ["scale10", "scale10", "scale10_matrix"] and inputs[0]["kind"] == "contradictory"  # 합친 문항은 불일치로 보낸다


def test_the_opportunity_question_is_always_first_and_comes_from_a_code_template(world):
    report = make_report(world)
    client = use_client(QuestionClient())
    run = world.session.get(PipelineRun, run_draft(world).json()["run_id"])
    opportunity, questions = drafts(world)
    assert opportunity.order_no == 1 and opportunity.hypothesis_id is None and opportunity.type == "scale10_matrix"
    assert opportunity.text == "다음 영역별로 개선이 필요한 정도를 눈금에서 골라 주세요." and opportunity.status == "draft"
    assert opportunity.options_json == {
        "kind": "opportunity_matrix", "low_label": "전혀 필요 없음", "high_label": "매우 필요함",
        "items": [{"code": "1", "label": "필름·소모품 비용"}, {"code": "2", "label": "현상·인화 대기"}, {"code": "3", "label": "사용법 안내"}, {"code": "4", "label": "결과물 품질"}],
    }
    assert opportunity.report_id == report.report_id and opportunity.run_id == run.run_id
    assert all(q.options_json["kind"] == "hypothesis" for q in questions)
    assert len(client.calls) == 1  # 영역 확인 문항을 위한 모델 호출은 없다
    # 모델에 가는 가설 입력에 영역 확인 문항은 없다
    assert len(json.loads(client.calls[0]["user_prompt"].split("\n", 1)[1])) == len(questions)


def test_no_opportunity_question_when_the_report_has_no_action_cards(world):
    report = make_report(world)
    for row in world.session.scalars(select(ActionSuggestion).where(ActionSuggestion.report_id == report.report_id)):
        row.sentence = "합성 설문에서 추천 응답이 49건이다."  # suggest-v3 형식의 문장
    world.session.commit()
    use_client(QuestionClient())
    run = world.session.get(PipelineRun, run_draft(world).json()["run_id"])
    rows = world.session.scalars(select(NextSurveyQuestion)).all()
    assert run.counters["opportunity_question"] == 0 and rows and all(q.hypothesis_id is not None for q in rows)
    assert [q.order_no for q in sorted(rows, key=lambda q: q.order_no)] == list(range(1, len(rows) + 1))


def test_the_same_hypothesis_gets_the_same_form_and_items_in_every_family_and_round(world):
    make_report(world)
    use_client(QuestionClient())
    run_draft(world)
    first = [(q.type, q.options_json["items"]) for q in drafts(world)[1]]
    # 다른 제품군·다른 회차의 스냅샷에서도 같은 가설이면 같은 형식과 항목이 나온다(설문이 제품군 공통이고 문항 정의가 회차마다 같다)
    from app.services.question_forms import decide_form
    from app.services.question_step import question_inputs, survey_options
    snapshot = snapshot_via_api(world, family_id=2)
    again = [(item["form"], item["items"]) for item in question_inputs(world.session, snapshot)]
    assert again == first
    q2 = world.session.scalar(select(Round).where(Round.label == "2026-Q2"))
    assert survey_options(world.session, q2.round_id) == survey_options(world.session, world.q1.round_id)
    assert decide_form(["survey:q06:2", "survey:q06:4"], survey_options(world.session, q2.round_id)).items == first[2][1]


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
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "failed" and run.error_code == "NO_HYPOTHESES" and run.counters["hypotheses"] == 0
    assert client.calls == [] and world.session.scalars(select(Hypothesis)).all() == []
    assert world.session.scalars(select(NextSurveyQuestion)).all() == []


def test_only_small_sample_hypothesis_fails_with_no_hypotheses_but_is_still_stored(world, monkeypatch):
    make_report(world)
    client = use_client(QuestionClient())
    only_r1 = [
        {"rule": "R1", "kind": "uncertain", "statement": "표본이 적다.", "related_row_ids": ["voc:judged:count"]},
    ]
    monkeypatch.setattr(question_step, "hypotheses_for", lambda session, snapshot: only_r1)
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "failed" and run.error_code == "NO_HYPOTHESES"
    assert run.counters["hypotheses"] == 1 and run.counters["question_hypotheses"] == 0
    assert client.calls == [] and world.session.scalars(select(NextSurveyQuestion)).all() == []
    assert len(world.session.scalars(select(Hypothesis)).all()) == 1


def test_meta_word_questions_are_dropped_with_their_own_counter(world):
    make_report(world)

    def mutate(questions):
        questions[0]["text"] = "수집된 의견을 어떻게 보시나요?"
        questions[1]["high_label"] = "표본이 많음"
        return questions

    use_client(QuestionClient(mutate=mutate))
    run = world.session.get(PipelineRun, run_draft(world).json()["run_id"])
    assert run.counters["dropped_meta"] == 2 and run.counters["dropped_reasons"] == {"meta_word": 2}
    assert run.counters["accepted"] == run.counters["question_hypotheses"] - 2


def test_invalid_questions_are_dropped_by_category(world):
    make_report(world)

    def mutate(questions):
        questions[0]["text"] = "월 3회 이상 쓰시나요?"  # 숫자
        questions[1]["low_label"] = ""  # 양끝 라벨이 비었다
        questions.append({**questions[2], "text": "같은 주제에 둘째 문항인가요?"})  # 같은 가설 둘째 문항
        questions.append({"hypothesis_id": 999999, "text": "없는 가설인가요?", "low_label": "아니다", "high_label": "그렇다"})
        return questions

    use_client(QuestionClient(mutate=mutate))
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "succeeded"
    c = run.counters
    assert c["dropped_number"] == 1 and c["dropped_hypothesis"] == 2 and c["dropped_format"] == 1
    assert c["dropped_reasons"] == {"has_number": 1, "bad_scale_label": 1, "duplicate_hypothesis": 1, "unknown_hypothesis": 1}
    assert c["accepted"] == c["question_hypotheses"] - 2 and c["proposed"] == c["question_hypotheses"] + 2
    # 문항 내용은 실행 기록에 없다
    assert "월 3회" not in json.dumps(c, ensure_ascii=False)
    # 시도마다 거부 사유가 코드 값으로 호출 기록에 남는다(내용은 남지 않는다)
    log = world.session.scalars(select(LlmCallLog).where(LlmCallLog.run_id == run.run_id)).all()
    assert len(log) == 1 and log[0].status == "ok"
    assert log[0].error_code == "dropped_hypothesis=2;dropped_format=1;dropped_number=1;has_number=1;bad_scale_label=1;duplicate_hypothesis=1;unknown_hypothesis=1"
    assert "월 3회" not in log[0].error_code


def test_model_output_that_tries_to_set_the_form_or_items_is_rejected_by_the_schema(world):
    make_report(world)
    client = use_client(QuestionClient(mutate=lambda qs: [{**q, "type": "single", "options": ["가", "나"]} for q in qs]))
    body = run_draft(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "failed" and run.error_code == "INVALID_OUTPUT" and run.counters["attempts"] == 3 == len(client.calls)
    assert world.session.scalars(select(NextSurveyQuestion)).all() == []  # 영역 확인 문항도 저장되지 않는다
    assert [l.status for l in world.session.scalars(select(LlmCallLog).where(LlmCallLog.run_id == run.run_id))] == ["invalid_output"] * 3


def test_a_question_that_lists_the_item_names_is_dropped(world):
    make_report(world)

    def mutate(questions):
        questions[2]["text"] = "여행, 모임·행사, 선물 중 어느 때에 많이 쓰시나요?"  # q06 매트릭스 문항이 항목 이름을 나열
        return questions

    use_client(QuestionClient(mutate=mutate))
    run = world.session.get(PipelineRun, run_draft(world).json()["run_id"])
    assert run.counters["dropped_reasons"] == {"lists_options": 1} and run.counters["dropped_format"] == 1


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
    assert run.counters["suggestions"] == 4 and run.counters["questions"] >= 1 and run.counters["report_id"]
    after = (len(world.session.scalars(select(Report)).all()), len(world.session.scalars(select(NextSurveyQuestion)).all()))
    assert before == after  # 새 데이터를 만들지 않는다


def test_report_assembly_without_any_report_is_not_ready(world):
    assert world.post(f"/api/rounds/{world.q1.round_id}/pipeline/report-assembly", json={"family_id": 1}).status_code == 400
    assert world.post(f"/api/rounds/{world.q1.round_id}/pipeline/report-assembly", json={"family_id": 99}).status_code == 404


# ---------- 같은 원문항에서 나온 가설 합치기 ----------
def test_hypotheses_from_the_same_source_question_become_one_question_and_keep_the_contradictory_mark(world):
    report = make_report(world)
    use_client(QuestionClient())
    run_draft(world)
    hypotheses = {h.hypothesis_id: h for h in world.session.scalars(select(Hypothesis))}
    _opportunity, questions = drafts(world)
    q09_questions = [q for q in questions if q.options_json["items"] == [] and q.hypothesis_id in hypotheses and hypotheses[q.hypothesis_id].kind == "contradictory"]
    assert len(q09_questions) == 1  # 추천 문항(q09)은 하나만 나온다
    merged_ids = q09_questions[0].options_json["merged_hypothesis_ids"]
    assert len(merged_ids) == 1 and hypotheses[merged_ids[0]].kind == "uncertain" and hypotheses[merged_ids[0]].related_row_ids[0].startswith("survey:q09")
    # 리포트 API: 대표 가설의 불일치 표시가 남고, 진술문에 합쳐진 가설의 진술문이 이어지며, 합쳐진 가설은 '문항이 없는 가설'에 나오지 않는다
    body = world.get(f"/api/reports/{report.report_id}").json()["next_survey"]
    api_q = next(q for q in body["questions"] if q["hypothesis_id"] == q09_questions[0].hypothesis_id)
    assert api_q["hypothesis_kind"] == "contradictory" and api_q["merged_hypothesis_ids"] == merged_ids
    assert hypotheses[q09_questions[0].hypothesis_id].statement in api_q["hypothesis_statement"] and hypotheses[merged_ids[0]].statement in api_q["hypothesis_statement"]
    assert [n["kind"] for n in body["no_question_hypotheses"]] == ["uncertain"] and "표본" in body["no_question_hypotheses"][0]["statement"]


def test_merge_by_source_prefers_the_contradictory_hypothesis_and_keeps_priority_order():
    from app.services.question_forms import merge_by_source

    items = [
        {"hypothesis_id": 1, "kind": "uncertain", "statement": "가", "source_question": "q10"},
        {"hypothesis_id": 2, "kind": "uncertain", "statement": "나", "source_question": "q09"},
        {"hypothesis_id": 3, "kind": "contradictory", "statement": "다", "source_question": "q09"},
        {"hypothesis_id": 4, "kind": "uncertain", "statement": "라", "source_question": "q06"},
    ]
    merged = merge_by_source(items)
    assert [m["source_question"] for m in merged] == ["q10", "q09", "q06"]  # 그룹의 첫 가설이 나온 순서
    q09 = merged[1]
    assert q09["hypothesis_id"] == 3 and q09["kind"] == "contradictory" and q09["statement"] == "다 나"  # 대표는 불일치 가설
    assert [m["hypothesis_id"] for m in q09["merged_items"]] == [2] and merged[0]["merged_items"] == []
    assert merge_by_source([]) == []
