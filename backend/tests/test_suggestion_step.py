"""step action-suggestions 전체 흐름(가짜 클라이언트). 실제 OpenAI는 호출하지 않고 모든 값은 가짜다."""

import json
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import get_session
from app.llm.client import LLMConfigError, LLMResult, PermanentLLMError, TransientLLMError
from app.llm.cost import CostGuard, Prices
from app.main import app
from app.models import (
    ActionSuggestion, AdJudgement, AnalysisSnapshot, LlmCallLog, PipelineRun, Product, ProductFamily, Report, Review, Round,
)
from app.routers.pipeline import get_llm_client_factory
from app.routers.steps import get_suggest_model_provider
from app.services.survey_load import load_synthetic_survey
from app.services.suggestion_step import run_action_suggestions, latest_snapshot
from app.services.synthetic_survey import generate
from tests.fakes import ScriptedClient

T0 = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
Q09 = "survey:q09:1"


def reviews(session, run_id):
    for review_id, rating, day, has_text, weight in (
        (1, 5, date(2026, 1, 1), True, 0.02), (2, 3, date(2026, 3, 31), True, 0.8),
        (3, 4, date(2026, 2, 10), True, None), (4, 2, date(2026, 2, 11), False, None),
    ):
        session.add(Review(review_id=review_id, product_name="pA", rating=rating, date=day, helpful_count=0,
                           title="제목" if has_text else None, review_text=None))
    session.flush()
    for review_id, weight in ((1, 0.02), (2, 0.8)):
        session.add(AdJudgement(review_id=review_id, run_id=run_id, status="ok", ad_probability=round(1 - weight, 6),
                                ad_weight=weight, judged_at=T0))


@pytest.fixture
def world(session):
    session.add_all([ProductFamily(name="일회용 카메라"), ProductFamily(name="인스탁스 즉석카메라")])
    session.add(Round(label="[파일럿-임시] 2026-11-02"))
    session.commit()
    load_synthetic_survey(session, generate())
    session.add(Product(product_name="pA", family_id=1))
    session.flush()
    q1 = session.scalar(select(Round).where(Round.label == "2026-Q1"))
    run = PipelineRun(round_id=q1.round_id, step="ad-judgement", status="succeeded", counters={}, started_at=T0)
    session.add(run)
    session.flush()
    reviews(session, run.run_id)
    session.commit()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app, raise_server_exceptions=False)
    client.session, client.q1 = session, q1
    yield client
    app.dependency_overrides.clear()


def set_llm(script, model="fake-model"):
    fake = ScriptedClient(script)
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda: fake)
    app.dependency_overrides[get_suggest_model_provider] = lambda: (lambda: model)
    return fake


def snapshot_via_api(world, family_id=1):
    response = world.post(f"/api/rounds/{world.q1.round_id}/pipeline/analysis-snapshot", json={"family_id": family_id})
    assert response.status_code == 201
    return latest_snapshot(world.session, family_id, world.q1.round_id)


def rows_of(snapshot):
    return {r["row_id"]: r for r in snapshot.table_json["rows"]}


def llm_text(*items):
    return LLMResult(text=json.dumps({"suggestions": [{"sentence": s, "row_ids": ids} for s, ids in items]}, ensure_ascii=False),
                     input_tokens=1500, output_tokens=300)


def good_sentences(snapshot):
    rows = rows_of(snapshot)
    yes = rows[Q09]["metrics"]["응답 수"]
    total = rows["voc:total:count"]["metrics"]["리뷰 수"]
    return (
        (f"합성 설문에서 지인에게 추천한 적이 있다는 응답이 {yes}건이라 추천 경로를 넓히는 안을 검토한다.", [Q09]),
        (f"VOC 전체 리뷰는 {total}건이다.", ["voc:total:count"]),
    )


def run_step(world, family_id=1):
    return world.post(f"/api/rounds/{world.q1.round_id}/pipeline/action-suggestions", json={"family_id": family_id})


def test_full_flow_saves_report_suggestions_and_counters(world):
    snapshot = snapshot_via_api(world)
    good = good_sentences(snapshot)
    bad_number = ("합성 설문에서 추천 응답이 9999건이다.", [Q09])
    fake = set_llm([llm_text(*good, bad_number)])
    response = run_step(world)
    assert response.status_code == 201
    body = response.json()
    assert body["step"] == "action-suggestions" and body["status"] == "succeeded"
    run = world.session.get(PipelineRun, body["run_id"])
    assert run.counters == {
        "proposed": 3, "accepted": 2, "dropped_no_evidence": 0, "dropped_number_mismatch": 1, "dropped_other": 0,
        "dropped_reasons": {}, "attempts": 1, "llm_calls": 1,
    }
    assert run.error_code is None and run.family_id == 1
    report = world.session.scalar(select(Report).where(Report.run_id == run.run_id))
    assert report.family_id == 1 and report.round_id == world.q1.round_id
    saved = world.session.scalars(select(ActionSuggestion).order_by(ActionSuggestion.order_no)).all()
    assert [s.order_no for s in saved] == [1, 2] and [s.sentence for s in saved] == [g[0] for g in good]
    assert saved[0].row_ids == [Q09] and all(s.snapshot_id == snapshot.snapshot_id for s in saved)
    log = world.session.scalars(select(LlmCallLog)).all()
    assert len(log) == 1 and log[0].call_type == "B" and log[0].status == "ok" and log[0].model_name == "fake-model"
    assert log[0].prompt_version == "suggest-v3" and (log[0].input_tokens, log[0].output_tokens) == (1500, 300)
    # 호출 B에는 근거 ID와 본문이 가지 않는다
    sent = fake.calls[0]["user_prompt"]
    assert "allowed_evidence" not in sent and "review_text" not in sent and fake.calls[0]["model"] == "fake-model"


def test_action_plan_and_evidence_counts_match_the_snapshot(world):
    snapshot = snapshot_via_api(world)
    set_llm([llm_text(*good_sentences(snapshot))])
    run_step(world)
    plan = world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()
    assert plan["report"]["report_id"] and [s["order_no"] for s in plan["action_plan"]] == [1, 2]
    first, second = plan["action_plan"]
    assert first["has_synthetic"] is True and second["has_synthetic"] is False
    assert first["evidence_count"] == {"review": 0, "survey": len(snapshot.allowed_evidence_json[Q09]["ids"])}
    assert second["evidence_count"] == {"review": 4, "survey": 0}  # 제품군 가의 2026-Q1 리뷰 4건(판정·미판정·제목 없음 포함)
    for item in plan["action_plan"]:  # 근거 건수 = A-10 목록의 total
        listed = world.get(f"/api/suggestions/{item['suggestion_id']}/evidence").json()
        assert listed["total"] == item["evidence_count"]["review"] + item["evidence_count"]["survey"]


def test_action_plan_empty_and_not_found(world):
    empty = world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()
    assert empty["report"] is None and empty["action_plan"] == []
    assert world.get("/api/families/99/action-plan?round_id=1").json()["error"]["code"] == "NOT_FOUND"
    pilot = world.session.scalar(select(Round.round_id).where(Round.label.like("[파일럿-임시]%")))
    assert world.get(f"/api/families/1/action-plan?round_id={pilot}").status_code == 404
    assert world.get("/api/families/1/action-plan").status_code == 422


def test_reruns_stack_and_the_latest_successful_report_is_shown(world):
    snapshot = snapshot_via_api(world)
    good = good_sentences(snapshot)
    set_llm([llm_text(good[0]), llm_text(good[1])])
    first, second = run_step(world).json(), run_step(world).json()
    assert len(world.session.scalars(select(Report)).all()) == 2
    plan = world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()
    assert plan["report"]["run_id"] == second["run_id"] != first["run_id"]
    assert [s["sentence"] for s in plan["action_plan"]] == [good[1][0]]


def test_step_not_ready_without_snapshot(world):
    set_llm([])
    response = run_step(world)
    assert response.status_code == 400 and response.json()["error"]["code"] == "STEP_NOT_READY"
    assert world.session.scalars(select(PipelineRun).where(PipelineRun.step == "action-suggestions")).all() == []


def test_zero_accepted_sentences_fail_the_run_after_three_requests(world):
    snapshot = snapshot_via_api(world)
    bad = llm_text(("합성 설문에서 추천 응답이 9999건이다.", [Q09]), ("근거가 없는 문장이다.", ["nope"]))
    fake = set_llm([bad, bad, bad])
    body = run_step(world).json()
    assert body["status"] == "failed"
    run = world.session.get(PipelineRun, body["run_id"])
    assert run.error_code == "NO_SUGGESTIONS"
    assert run.counters["attempts"] == 3 and run.counters["llm_calls"] == 3 == len(fake.calls)
    assert (run.counters["proposed"], run.counters["accepted"], run.counters["dropped_number_mismatch"], run.counters["dropped_no_evidence"]) == (2, 0, 1, 1)
    assert world.session.scalars(select(Report)).all() == [] and world.session.scalars(select(ActionSuggestion)).all() == []
    assert [row.status for row in world.session.scalars(select(LlmCallLog))] == ["invalid_output"] * 3


def test_broken_schema_then_valid_output_succeeds_on_the_second_request(world):
    snapshot = snapshot_via_api(world)
    set_llm([LLMResult(text="not json", input_tokens=10, output_tokens=5), llm_text(*good_sentences(snapshot))])
    body = run_step(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "succeeded" and run.counters["attempts"] == 2 and run.counters["llm_calls"] == 2
    assert run.counters["accepted"] == 2


def test_dropped_other_for_missing_synthetic_and_small_sample_words(world):
    snapshot = snapshot_via_api(world)
    rows = rows_of(snapshot)
    yes = rows[Q09]["metrics"]["응답 수"]
    judged = rows["voc:judged:count"]["metrics"]["건수"]
    items = (
        (f"추천한 적이 있다는 응답이 {yes}건이다.", [Q09]),  # 합성 누락
        (f"판정된 글은 {judged}건이다.", ["voc:judged:count"]),  # 표본 누락 (small_sample 참)
        (f"표본이 적지만 판정된 글은 {judged}건이다.", ["voc:judged:count"]),  # 통과
    )
    set_llm([llm_text(*items)])
    run = world.session.get(PipelineRun, run_step(world).json()["run_id"])
    assert run.counters["dropped_other"] == 2 and run.counters["accepted"] == 1


def test_config_errors_and_cost_limit_do_not_create_runs(world, monkeypatch):
    snapshot_via_api(world)
    app.dependency_overrides.pop(get_suggest_model_provider, None)
    app.dependency_overrides[get_llm_client_factory] = lambda: (lambda: ScriptedClient([]))
    response = run_step(world)  # OPENAI_MODEL_SUGGEST가 없다
    assert response.status_code == 500 and response.json()["error"]["code"] == "MODEL_NOT_CONFIGURED"
    set_llm([])

    def no_key():
        raise LLMConfigError("키 없음")

    app.dependency_overrides[get_llm_client_factory] = lambda: no_key
    assert run_step(world).json()["error"]["code"] == "LLM_NOT_CONFIGURED"
    set_llm([])
    monkeypatch.delenv("OPENAI_PRICE_INPUT_PER_M")
    assert run_step(world).json()["error"]["code"] == "PRICE_NOT_CONFIGURED"
    monkeypatch.setenv("OPENAI_PRICE_INPUT_PER_M", "0.20")
    monkeypatch.setenv("SUGGESTION_COST_LIMIT_USD", "0.000001")
    response = run_step(world)
    assert response.status_code == 422 and response.json()["error"]["code"] == "COST_LIMIT_EXCEEDED"
    assert world.session.scalars(select(PipelineRun).where(PipelineRun.step == "action-suggestions")).all() == []


def test_request_validation(world):
    set_llm([])
    q1 = world.q1.round_id
    assert world.post(f"/api/rounds/{q1}/pipeline/action-suggestions", json={}).status_code == 422
    assert world.post(f"/api/rounds/{q1}/pipeline/action-suggestions", json={"family_id": 99}).status_code == 404
    assert world.post(f"/api/rounds/999/pipeline/action-suggestions", json={"family_id": 1}).status_code == 404


# ---------- 서비스 직접 호출: 재시도, 대기, 비용 가드 ----------
def service_inputs(world):
    snapshot = snapshot_via_api(world)
    family = world.session.get(ProductFamily, 1)
    return family, snapshot


def call_service(world, client, **kwargs):
    family, snapshot = service_inputs(world)
    sleeps = []
    run = run_action_suggestions(
        world.session, round_row=world.q1, family=family, snapshot=snapshot, client=client, model_name="fake-model",
        sleep=sleeps.append, **kwargs,
    )
    return run, sleeps, snapshot


def test_transient_errors_are_retried_with_growing_waits(world):
    snapshot = snapshot_via_api(world)
    client = ScriptedClient([TransientLLMError("TIMEOUT"), TransientLLMError("RATE_LIMIT"), llm_text(*good_sentences(snapshot))])
    run, sleeps, _ = call_service(world, client)
    assert run.status == "succeeded" and sleeps == [1, 2] and run.counters["llm_calls"] == 3 and run.counters["attempts"] == 1
    logs = world.session.scalars(select(LlmCallLog).order_by(LlmCallLog.call_id)).all()
    assert [(l.status, l.error_code) for l in logs] == [("api_error", "TIMEOUT"), ("api_error", "RATE_LIMIT"), ("ok", None)]


def test_transient_errors_exhaust_after_three_retries(world):
    client = ScriptedClient([TransientLLMError("TIMEOUT")] * 4)
    run, sleeps, _ = call_service(world, client)
    assert run.status == "failed" and run.error_code == "TIMEOUT" and sleeps == [1, 2, 4] and run.counters["llm_calls"] == 4


def test_permanent_error_is_not_retried(world):
    client = ScriptedClient([PermanentLLMError("HTTP_401")])
    run, sleeps, _ = call_service(world, client)
    assert run.status == "failed" and run.error_code == "HTTP_401" and sleeps == [] and len(client.calls) == 1


def test_cost_guard_stops_retries_when_the_limit_is_exceeded(world):
    bad = LLMResult(text="not json", input_tokens=1_000_000, output_tokens=0)
    client = ScriptedClient([bad, bad, bad])
    run, _, _ = call_service(world, client, cost_guard=CostGuard(0.01, Prices(0.20, 1.20)))
    assert run.status == "failed" and run.error_code == "COST_LIMIT" and len(client.calls) == 1


def test_internal_error_marks_the_run_failed_without_details(world):
    class Boom:
        def complete_json(self, **kwargs):
            raise RuntimeError("비밀 접속 문자열 postgresql://u:p@h/db")

    run, _, _ = call_service(world, Boom())
    assert run.status == "failed" and run.error_code == "INTERNAL_ERROR"
    assert "postgresql" not in json.dumps(run.counters) and "postgresql" not in (run.error_code or "")
