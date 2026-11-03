"""step action-suggestions(suggest-v4 액션 카드) 전체 흐름(가짜 클라이언트). 실제 OpenAI는 호출하지 않고 모든 값은 가짜다."""

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
from app.services import suggestion_step
from app.services.action_cards import render_area_card
from app.services.survey_load import load_synthetic_survey
from app.services.suggestion_step import areas_for, run_action_suggestions, latest_snapshot
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


SENTENCE = "이 영역을 개선 희망으로 고른 응답자는 {pct}이며 {rank}입니다."
DELIVERABLE = "자주 묻는 질문과 답변 초안입니다. 기간과 비용은 [확인 필요]입니다."


def card(code, sentence=SENTENCE, kind="FAQ 초안", text=DELIVERABLE):
    return {"area_code": code, "priority_sentence": sentence, "deliverable_kind": kind, "deliverable_text": text}


def llm_text(*items):
    return LLMResult(text=json.dumps({"cards": list(items)}, ensure_ascii=False), input_tokens=1500, output_tokens=300)


def good_cards(world, snapshot):
    return [card(area.code) for area in areas_for(world.session, snapshot)]


def good_response(world, snapshot):
    return llm_text(*good_cards(world, snapshot))


def run_step(world, family_id=1):
    return world.post(f"/api/rounds/{world.q1.round_id}/pipeline/action-suggestions", json={"family_id": family_id})


def test_full_flow_saves_report_cards_and_counters(world):
    snapshot = snapshot_via_api(world)
    areas = areas_for(world.session, snapshot)
    assert len(areas) == 3
    fake = set_llm([good_response(world, snapshot)])
    response = run_step(world)
    assert response.status_code == 201
    body = response.json()
    assert body["step"] == "action-suggestions" and body["status"] == "succeeded"
    run = world.session.get(PipelineRun, body["run_id"])
    assert run.counters == {
        "proposed": 3, "accepted": 3, "dropped_no_evidence": 0, "dropped_number_mismatch": 0, "dropped_other": 0,
        "dropped_reasons": {}, "areas": 3, "attempts": 1, "llm_calls": 1,
    }
    assert run.error_code is None and run.family_id == 1
    report = world.session.scalar(select(Report).where(Report.run_id == run.run_id))
    assert report.family_id == 1 and report.round_id == world.q1.round_id
    saved = world.session.scalars(select(ActionSuggestion).order_by(ActionSuggestion.order_no)).all()
    assert [s.order_no for s in saved] == [1, 2, 3, 4]  # 영역 카드 3개 + 쿠팡 리뷰 카드 1개
    for area, row in zip(areas, saved):
        assert row.sentence == render_area_card(area, SENTENCE, "FAQ 초안", DELIVERABLE)
        assert row.row_ids == area.row_ids
        assert "{pct}" not in row.sentence and "{rank}" not in row.sentence and f"{area.pct}%" in row.sentence and area.rank_label in row.sentence
        assert row.sentence.startswith(f"합성 설문 기준 '{area.label}' 영역 — ")
    assert saved[3].sentence.startswith("쿠팡 리뷰 기준(실측) — ") and saved[3].row_ids == ["voc:total:count", "voc:no_text:count", "voc:judged:count"]
    assert all(s.snapshot_id == snapshot.snapshot_id for s in saved)
    log = world.session.scalars(select(LlmCallLog)).all()
    assert len(log) == 1 and log[0].call_type == "B" and log[0].status == "ok" and log[0].model_name == "fake-model"
    assert log[0].prompt_version == "suggest-v4" and (log[0].input_tokens, log[0].output_tokens) == (1500, 300) and log[0].item_count == 3
    # 호출 B에는 영역 코드·라벨·순위 라벨만 간다: 표, 수치, 근거 ID, 리뷰 본문은 가지 않는다
    sent = fake.calls[0]["user_prompt"]
    assert fake.calls[0]["model"] == "fake-model"
    assert json.loads(sent.split("\n", 1)[1]) == [{"area_code": a.code, "label": a.label, "rank_label": a.rank_label} for a in areas]
    assert "allowed_evidence" not in sent and "review_text" not in sent and "voc:" not in sent and "survey:" not in sent


def test_the_review_card_is_a_code_template_and_mentions_the_small_sample(world):
    snapshot = snapshot_via_api(world)
    fake = set_llm([good_response(world, snapshot)])
    run_step(world)
    review = world.session.scalars(select(ActionSuggestion).order_by(ActionSuggestion.order_no)).all()[3]
    rows = rows_of(snapshot)
    total, no_text, judged = rows["voc:total:count"]["metrics"]["리뷰 수"], rows["voc:no_text:count"]["metrics"]["건수"], rows["voc:judged:count"]["metrics"]["건수"]
    assert review.sentence == (
        f"쿠팡 리뷰 기준(실측) — 선택한 회차의 리뷰는 {total}건이고, 그중 제목·본문 없음이 {no_text}건, 판정이 끝난 글이 {judged}건이다. "
        "판정 표본이 적어 영역 우선순위는 설문 기준으로만 정했다."
    )
    assert len(fake.calls) == 1  # 리뷰 카드를 위한 모델 호출은 없다


def test_action_plan_and_evidence_counts_match_the_snapshot(world):
    snapshot = snapshot_via_api(world)
    areas = areas_for(world.session, snapshot)
    set_llm([good_response(world, snapshot)])
    run_step(world)
    plan = world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()
    assert plan["report"]["report_id"] and [s["order_no"] for s in plan["action_plan"]] == [1, 2, 3, 4]
    assert [s["has_synthetic"] for s in plan["action_plan"]] == [True, True, True, False]
    evidence = snapshot.allowed_evidence_json
    for area, item in zip(areas, plan["action_plan"]):
        expected = set().union(*(set(evidence[row_id]["ids"]) for row_id in area.row_ids))  # q08 해당 보기 합집합 q07 같은 영역 보기
        assert item["evidence_count"] == {"review": 0, "survey": len(expected)}
    assert plan["action_plan"][3]["evidence_count"] == {"review": 4, "survey": 0}  # 제품군 가의 2026-Q1 리뷰 4건(판정·미판정·제목 없음 포함)
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
    set_llm([good_response(world, snapshot), good_response(world, snapshot)])
    first, second = run_step(world).json(), run_step(world).json()
    assert len(world.session.scalars(select(Report)).all()) == 2
    plan = world.get(f"/api/families/1/action-plan?round_id={world.q1.round_id}").json()
    assert plan["report"]["run_id"] == second["run_id"] != first["run_id"]
    assert len(plan["action_plan"]) == 4


def test_step_not_ready_without_snapshot(world):
    set_llm([])
    response = run_step(world)
    assert response.status_code == 400 and response.json()["error"]["code"] == "STEP_NOT_READY"
    assert world.session.scalars(select(PipelineRun).where(PipelineRun.step == "action-suggestions")).all() == []


def test_zero_accepted_cards_fail_the_run_after_three_requests(world):
    snapshot = snapshot_via_api(world)
    areas = areas_for(world.session, snapshot)
    bad = llm_text(*[card(a.code, sentence="이 영역은 33.0%이며 {rank}입니다.") for a in areas])  # 숫자를 직접 씀
    fake = set_llm([bad, bad, bad])
    body = run_step(world).json()
    assert body["status"] == "failed"
    run = world.session.get(PipelineRun, body["run_id"])
    assert run.error_code == "NO_SUGGESTIONS"
    assert run.counters["attempts"] == 3 and run.counters["llm_calls"] == 3 == len(fake.calls)
    assert (run.counters["proposed"], run.counters["accepted"], run.counters["dropped_number_mismatch"], run.counters["dropped_other"]) == (3, 0, 3, 3)
    assert run.counters["dropped_reasons"] == {"missing_area": 3}
    assert world.session.scalars(select(Report)).all() == [] and world.session.scalars(select(ActionSuggestion)).all() == []
    assert [row.status for row in world.session.scalars(select(LlmCallLog))] == ["invalid_output"] * 3


def test_broken_schema_then_valid_output_succeeds_on_the_second_request(world):
    snapshot = snapshot_via_api(world)
    set_llm([LLMResult(text="not json", input_tokens=10, output_tokens=5), good_response(world, snapshot)])
    body = run_step(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "succeeded" and run.counters["attempts"] == 2 and run.counters["llm_calls"] == 2
    assert run.counters["accepted"] == 3


def test_a_response_missing_an_area_is_rejected_and_retried(world):
    snapshot = snapshot_via_api(world)
    cards = good_cards(world, snapshot)
    set_llm([llm_text(*cards[:2]), llm_text(*cards)])
    body = run_step(world).json()
    run = world.session.get(PipelineRun, body["run_id"])
    assert body["status"] == "succeeded" and run.counters["attempts"] == 2
    assert [row.status for row in world.session.scalars(select(LlmCallLog).order_by(LlmCallLog.call_id))] == ["invalid_output", "ok"]
    assert len(world.session.scalars(select(ActionSuggestion)).all()) == 4  # 불완전한 응답의 카드는 저장되지 않았다


def test_unknown_and_duplicate_area_codes_are_counted_but_a_complete_set_is_accepted(world):
    snapshot = snapshot_via_api(world)
    cards = good_cards(world, snapshot)
    extra = [card("9"), card(cards[0]["area_code"])]  # 알 수 없는 area_code, 중복 area_code
    set_llm([llm_text(*cards, *extra)])
    run = world.session.get(PipelineRun, run_step(world).json()["run_id"])
    assert run.status == "succeeded"
    assert (run.counters["proposed"], run.counters["accepted"], run.counters["dropped_no_evidence"], run.counters["dropped_other"]) == (5, 3, 1, 1)
    assert run.counters["dropped_reasons"] == {"duplicate_area": 1}


def test_a_joint_word_written_by_the_model_is_rejected(world):
    snapshot = snapshot_via_api(world)
    areas = areas_for(world.session, snapshot)
    cards = [card(a.code, sentence="이 영역은 {pct}이며 공동 {rank}입니다.") for a in areas]
    set_llm([llm_text(*cards)] * 3)
    run = world.session.get(PipelineRun, run_step(world).json()["run_id"])
    assert run.status == "failed" and run.counters["dropped_reasons"].get("rank_label_mismatch") == 3


def test_no_candidate_area_fails_without_calling_the_model(world, monkeypatch):
    snapshot_via_api(world)
    monkeypatch.setattr(suggestion_step, "option_labels", lambda session, round_id: {})
    fake = set_llm([])
    run = world.session.get(PipelineRun, run_step(world).json()["run_id"])
    assert run.status == "failed" and run.error_code == "NO_SUGGESTIONS" and run.counters["areas"] == 0 and fake.calls == []


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
    client = ScriptedClient([TransientLLMError("TIMEOUT"), TransientLLMError("RATE_LIMIT"), good_response(world, snapshot)])
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
