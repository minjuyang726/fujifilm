import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import get_session
from app.llm.client import PermanentLLMError, TransientLLMError
from app.llm.prompts.ad_judgement import PROMPT_VERSION
from app.main import app
from app.models import AdJudgement, LlmCallLog, PipelineRun, Product, Review, Round
from app.routers.pipeline import get_ad_model_provider, get_llm_client_factory
from app.services import ad_judgement as service
from app.services.ad_judgement_step import run_ad_judgement_step
from tests.fakes import EchoClient, ScriptedClient, prompt_ids

SECRET_TEXT = "비밀본문-절대-로그에-남기면-안-됨"
SECRET_TITLE = "비밀제목-절대-로그에-남기면-안-됨"
MODEL = "test-model-name"
ALL = {"review_ids": [1, 2, 3, 4, 5]}  # 시험 데이터의 리뷰 전부


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    monkeypatch.setattr(service, "BACKOFF_SECONDS", (0.0, 0.0, 0.0))


@pytest.fixture
def seeded(session):
    session.add(Product(product_name="상품A"))
    session.add(Round(label="2026Q4"))
    session.flush()
    rows = [
        # 제목+본문, 본문만, 제목만 -> 판정 대상 3건
        (1, SECRET_TITLE, SECRET_TEXT),
        (2, None, SECRET_TEXT),
        (3, SECRET_TITLE, None),
        # 둘 다 없음 -> skipped 2건
        (4, None, None),
        (5, None, None),
    ]
    for review_id, title, text in rows:
        session.add(
            Review(
                review_id=review_id, product_name="상품A", rating=5, date=__import__("datetime").date(2026, 1, 1),
                variant="옵션", helpful_count=0, title=title, review_text=text,
            )
        )
    session.commit()
    return session


def make_api(session_factory, client=None, model=MODEL):
    def override_session():
        with session_factory() as db_session:
            yield db_session

    app.dependency_overrides[get_session] = override_session
    if client is not None:
        app.dependency_overrides[get_llm_client_factory] = lambda: (lambda: client)
    if model is not None:
        app.dependency_overrides[get_ad_model_provider] = lambda: (lambda: model)
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_post_creates_a_run_and_get_returns_counters(seeded, session_factory):
    api = make_api(session_factory, EchoClient())
    response = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL)
    assert response.status_code == 201
    created = response.json()
    assert set(created) == {"run_id", "step", "status", "started_at"}
    assert created["step"] == "ad-judgement" and created["status"] == "succeeded"

    detail = api.get(f"/api/runs/{created['run_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert set(body) == {
        "run_id", "round_id", "family_id", "step", "status", "counters", "error_code", "started_at", "finished_at",
    }
    assert body["counters"] == {"eligible": 3, "skipped": 2, "sent": 3, "ok": 3, "failed": 0, "not_run": 0}
    assert body["round_id"] == 1 and body["family_id"] is None
    assert body["error_code"] is None and body["finished_at"] is not None


def test_judgement_rows_follow_the_rules(seeded, session_factory):
    make_api(session_factory, EchoClient()).post("/api/rounds/1/pipeline/ad-judgement", json=ALL)
    seeded.expire_all()
    rows = {row.review_id: row for row in seeded.scalars(select(AdJudgement))}
    assert len(rows) == 5
    # 제목 또는 본문이 있는 3건은 판정되고 가중치는 1 - 확률이다(하한 없음).
    for review_id in (1, 2, 3):
        row = rows[review_id]
        assert row.status == "ok"
        assert row.ad_probability == (review_id % 10) / 10
        assert row.ad_weight == pytest.approx(1 - row.ad_probability)
        assert row.model_name == MODEL and row.prompt_version == PROMPT_VERSION
    # 둘 다 없는 2건은 LLM에 보내지 않고 skipped
    for review_id in (4, 5):
        row = rows[review_id]
        assert (row.status, row.ad_probability, row.ad_weight, row.model_name) == ("skipped", None, None, None)


def test_call_log_records_model_prompt_version_and_tokens_without_text(seeded, session_factory):
    make_api(session_factory, EchoClient()).post("/api/rounds/1/pipeline/ad-judgement", json=ALL)
    seeded.expire_all()
    logs = seeded.scalars(select(LlmCallLog)).all()
    assert len(logs) == 1
    log = logs[0]
    assert (log.call_type, log.model_name, log.prompt_version) == ("A", MODEL, PROMPT_VERSION)
    assert (log.status, log.attempt_no, log.item_count) == ("ok", 1, 3)
    assert (log.input_tokens, log.output_tokens) == (11, 7)
    assert log.latency_ms is not None and log.created_at is not None
    columns = {column.name for column in LlmCallLog.__table__.columns}
    assert not (columns & {"prompt", "response", "review_text", "title", "text", "api_key"})


def test_step_cap_is_a_second_guard_that_limits_how_many_reviews_are_sent(seeded):
    # API는 상한을 넘는 목록을 먼저 거절하므로, 단계 함수의 상한은 직접 불러서 확인한다.
    run = run_ad_judgement_step(
        seeded, round_id=1, family_id=None, client=EchoClient(), model_name=MODEL, max_items=2,
        review_ids=ALL["review_ids"], sleep=lambda _seconds: None,
    )
    assert run.counters == {"eligible": 3, "skipped": 2, "sent": 2, "ok": 2, "failed": 0, "not_run": 1}
    seeded.expire_all()
    assert count(seeded, AdJudgement) == 4  # skipped 2 + 판정 2. 상한을 넘은 글은 기록하지 않는다.


def test_default_cap_is_one_hundred():
    from app.config import get_settings

    assert get_settings().ad_judgement_max_items == 100


def test_partial_when_one_review_keeps_failing(seeded, session_factory):
    api = make_api(session_factory, EchoClient(omit={2}))
    run_id = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL).json()["run_id"]
    body = api.get(f"/api/runs/{run_id}").json()
    assert body["status"] == "partial"
    assert body["counters"]["ok"] == 2 and body["counters"]["failed"] == 1
    assert body["error_code"] == "INVALID_OUTPUT"
    seeded.expire_all()
    failed = seeded.scalars(select(AdJudgement).where(AdJudgement.status == "failed")).all()
    assert [(row.review_id, row.ad_probability, row.ad_weight) for row in failed] == [(2, None, None)]
    # 1번 호출 + 검증 실패 재시도 2번
    assert seeded.scalar(select(func.max(LlmCallLog.attempt_no))) == 3


def test_failed_when_every_review_fails(seeded, session_factory):
    client = ScriptedClient([TransientLLMError("RATE_LIMIT")] * 4)
    api = make_api(session_factory, client)
    run_id = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL).json()["run_id"]
    body = api.get(f"/api/runs/{run_id}").json()
    assert body["status"] == "failed" and body["error_code"] == "RATE_LIMIT"
    assert body["counters"]["ok"] == 0 and body["counters"]["failed"] == 3
    seeded.expire_all()
    assert count(seeded, LlmCallLog) == 4


def test_permanent_error_fails_the_run_and_counts_unsent_reviews(seeded, session_factory):
    api = make_api(session_factory, ScriptedClient([PermanentLLMError("HTTP_401")]))
    run_id = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL).json()["run_id"]
    body = api.get(f"/api/runs/{run_id}").json()
    assert body["status"] == "failed" and body["error_code"] == "HTTP_401"


def test_unexpected_error_marks_the_run_failed_and_keeps_no_partial_rows(seeded, session_factory):
    class Broken:
        def complete_json(self, **_kwargs):
            raise RuntimeError(SECRET_TEXT)

    api = make_api(session_factory, Broken())
    response = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL)
    assert response.status_code == 201 and response.json()["status"] == "failed"
    body = api.get(f"/api/runs/{response.json()['run_id']}").json()
    assert body["error_code"] == "INTERNAL_ERROR"
    assert SECRET_TEXT not in response.text and SECRET_TEXT not in str(body)
    seeded.expire_all()
    assert count(seeded, AdJudgement) == 0


def test_missing_round_is_404_and_creates_no_run(seeded, session_factory):
    api = make_api(session_factory, EchoClient())
    response = api.post("/api/rounds/999/pipeline/ad-judgement", json=ALL)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"
    seeded.expire_all()
    assert count(seeded, PipelineRun) == 0


def test_missing_run_is_404(session_factory):
    api = make_api(session_factory)
    assert api.get("/api/runs/12345").status_code == 404


@pytest.mark.parametrize("payload", [{"family_id": "abc"}, {"unknown": 1}, {"family_id": 1, "x": 2}, [1, 2]])
def test_bad_body_is_422(seeded, session_factory, payload):
    api = make_api(session_factory, EchoClient())
    assert api.post("/api/rounds/1/pipeline/ad-judgement", json=payload).status_code == 422


def test_bad_path_values_are_422(seeded, session_factory):
    api = make_api(session_factory, EchoClient())
    assert api.post("/api/rounds/abc/pipeline/ad-judgement", json={}).status_code == 422
    assert api.get("/api/runs/abc").status_code == 422


def sent_ids(client):
    return sorted(review_id for call in client.calls for review_id in prompt_ids(call["user_prompt"]))


def test_review_ids_send_exactly_those_reviews_even_when_smaller_ids_exist(seeded, session_factory):
    client = EchoClient()
    api = make_api(session_factory, client)
    # 번호가 작은 1번이 있어도 지정한 2, 3번만 보낸다(표본과 실제 전송이 같아야 한다).
    run_id = api.post("/api/rounds/1/pipeline/ad-judgement", json={"review_ids": [3, 2, 3]}).json()["run_id"]
    assert sent_ids(client) == [2, 3]
    assert api.get(f"/api/runs/{run_id}").json()["counters"] == {
        "eligible": 2, "skipped": 0, "sent": 2, "ok": 2, "failed": 0, "not_run": 0,
    }
    seeded.expire_all()
    assert sorted(row.review_id for row in seeded.scalars(select(AdJudgement))) == [2, 3]


def test_review_ids_with_a_skippable_review_records_skipped_without_sending_it(seeded, session_factory):
    client = EchoClient()
    api = make_api(session_factory, client)
    run_id = api.post("/api/rounds/1/pipeline/ad-judgement", json={"review_ids": [1, 4]}).json()["run_id"]
    assert sent_ids(client) == [1]
    counters = api.get(f"/api/runs/{run_id}").json()["counters"]
    assert (counters["eligible"], counters["skipped"], counters["sent"]) == (1, 1, 1)


@pytest.mark.parametrize("payload", [None, {}, {"family_id": 7}, {"review_ids": None}])
def test_missing_review_ids_is_rejected_and_nothing_is_sent(seeded, session_factory, payload):
    client = EchoClient()
    api = make_api(session_factory, client)
    response = api.post("/api/rounds/1/pipeline/ad-judgement", **({} if payload is None else {"json": payload}))
    assert response.status_code == 422
    assert client.calls == []
    seeded.expire_all()
    assert count(seeded, PipelineRun) == 0


@pytest.mark.parametrize("review_ids", [[], [0], [-1], ["a"], [1.5]])
def test_bad_review_ids_are_422_and_nothing_is_sent(seeded, session_factory, review_ids):
    client = EchoClient()
    api = make_api(session_factory, client)
    assert api.post("/api/rounds/1/pipeline/ad-judgement", json={"review_ids": review_ids}).status_code == 422
    assert client.calls == []
    seeded.expire_all()
    assert count(seeded, PipelineRun) == 0


def test_unknown_review_id_is_rejected_as_a_whole(seeded, session_factory):
    client = EchoClient()
    api = make_api(session_factory, client)
    response = api.post("/api/rounds/1/pipeline/ad-judgement", json={"review_ids": [1, 2, 999]})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNKNOWN_REVIEW_IDS"
    assert "999" not in response.text
    assert client.calls == []
    seeded.expire_all()
    assert count(seeded, PipelineRun) == 0


def test_review_ids_over_the_cap_are_rejected_not_cut(seeded, session_factory, monkeypatch):
    monkeypatch.setenv("AD_JUDGEMENT_MAX_ITEMS", "2")
    client = EchoClient()
    api = make_api(session_factory, client)
    response = api.post("/api/rounds/1/pipeline/ad-judgement", json={"review_ids": [1, 2, 3]})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "TOO_MANY_REVIEWS"
    assert client.calls == []


def test_family_id_is_recorded(seeded, session_factory):
    api = make_api(session_factory, EchoClient())
    run_id = api.post("/api/rounds/1/pipeline/ad-judgement", json={**ALL, "family_id": 7}).json()["run_id"]
    assert api.get(f"/api/runs/{run_id}").json()["family_id"] == 7


def test_missing_model_name_is_a_clear_500_and_creates_no_run(seeded, session_factory):
    api = make_api(session_factory, EchoClient(), model=None)  # 모델 의존성을 대체하지 않는다 -> 환경 값 없음
    response = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "MODEL_NOT_CONFIGURED"
    seeded.expire_all()
    assert count(seeded, PipelineRun) == 0


def test_default_client_without_openai_key_is_a_clear_500(seeded, session_factory):
    api = make_api(session_factory, client=None)  # 기본 클라이언트 사용, 키 없음
    response = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL)
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "LLM_NOT_CONFIGURED"
    assert "OPENAI_API_KEY" not in response.text or "설정" in response.text
    seeded.expire_all()
    assert count(seeded, PipelineRun) == 0


def test_responses_and_logs_never_contain_review_text_author_or_variant(seeded, session_factory, caplog):
    caplog.set_level(logging.DEBUG)
    api = make_api(session_factory, EchoClient(omit={2}))
    run_id = api.post("/api/rounds/1/pipeline/ad-judgement", json=ALL).json()["run_id"]
    texts = [api.get(f"/api/runs/{run_id}").text, caplog.text]
    for text in texts:
        for forbidden in (SECRET_TEXT, SECRET_TITLE, "author", "variant", "옵션"):
            assert forbidden not in text
