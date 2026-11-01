import pytest

from app.llm.client import PermanentLLMError, TransientLLMError
from app.llm.prompts.ad_judgement import SYSTEM_PROMPT
from app.services import ad_judgement as service
from app.services.ad_judgement import ReviewInput, judge_reviews
from tests.fakes import EchoClient, ScriptedClient, ok_result, prompt_items, results_text
from app.llm.client import LLMResult


def reviews(count, start=1):
    return [ReviewInput(i, f"제목{i}", f"본문{i}") for i in range(start, start + count)]


def run(client, items, **kwargs):
    records = []
    sleeps = []
    report = judge_reviews(
        client, "test-model", items, sleep=sleeps.append, on_call=records.append, **kwargs
    )
    return report, records, sleeps


def test_normal_response_judges_every_review_in_batches_of_ten():
    client = EchoClient()
    report, records, _ = run(client, reviews(25))
    assert [len(ids) for ids in [[i for i in prompt_items(c["user_prompt"])] for c in client.calls]] == [10, 10, 5]
    assert len(report.outcomes) == 25
    assert all(outcome.status == "ok" for outcome in report.outcomes)
    assert [outcome.ad_probability for outcome in report.outcomes[:3]] == [0.1, 0.2, 0.3]
    assert [record.status for record in records] == ["ok", "ok", "ok"]
    assert all(record.input_tokens == 11 and record.output_tokens == 7 for record in records)
    assert not report.aborted and report.not_run == []


def test_count_mismatch_retries_only_the_missing_item():
    client = ScriptedClient([ok_result([(1, 0.1), (3, 0.3)]), ok_result([(2, 0.2)])])
    report, records, _ = run(client, reviews(3))
    assert client.ids_per_call() == [[1, 2, 3], [2]]
    assert {o.review_id: o.ad_probability for o in report.outcomes} == {1: 0.1, 2: 0.2, 3: 0.3}
    assert [record.status for record in records] == ["invalid_output", "ok"]
    assert "length_mismatch" in records[0].error_code


def test_missing_review_id_is_retried():
    client = ScriptedClient([ok_result([(1, 0.1), (2, 0.2)]), ok_result([(3, 0.3)])])
    report, _, _ = run(client, reviews(3))
    assert client.ids_per_call()[1] == [3]
    assert all(outcome.status == "ok" for outcome in report.outcomes)


def test_duplicate_review_id_is_retried():
    client = ScriptedClient([ok_result([(1, 0.1), (1, 0.9), (2, 0.2)]), ok_result([(1, 0.5)])])
    report, _, _ = run(client, reviews(2))
    assert client.ids_per_call() == [[1, 2], [1]]
    assert {o.review_id: o.ad_probability for o in report.outcomes} == {1: 0.5, 2: 0.2}


def test_probability_out_of_range_is_retried():
    client = ScriptedClient([ok_result([(1, 1.5), (2, 0.2)]), ok_result([(1, 0.9)])])
    report, _, _ = run(client, reviews(2))
    assert client.ids_per_call() == [[1, 2], [1]]
    assert {o.review_id: o.ad_probability for o in report.outcomes} == {1: 0.9, 2: 0.2}


def test_failing_after_validation_retries_marks_failed_without_inventing_a_value():
    bad = LLMResult(text="not json", input_tokens=None, output_tokens=None)
    client = ScriptedClient([bad, bad, bad])
    report, records, _ = run(client, reviews(2))
    # 처음 한 번 + 검증 실패 재시도 2번
    assert len(client.calls) == 1 + service.MAX_VALIDATION_RETRIES
    assert [outcome.status for outcome in report.outcomes] == ["failed", "failed"]
    assert all(outcome.ad_probability is None for outcome in report.outcomes)
    assert all(outcome.error_code == service.ERROR_INVALID_OUTPUT for outcome in report.outcomes)
    assert [record.status for record in records] == ["invalid_output"] * 3


def test_transient_errors_are_retried_with_growing_waits():
    client = ScriptedClient(
        [TransientLLMError("RATE_LIMIT"), TransientLLMError("TIMEOUT"), ok_result([(1, 0.1)])]
    )
    report, records, sleeps = run(client, reviews(1))
    assert report.outcomes[0].status == "ok"
    assert sleeps == [1.0, 2.0]
    assert [record.status for record in records] == ["api_error", "api_error", "ok"]
    assert [record.error_code for record in records[:2]] == ["RATE_LIMIT", "TIMEOUT"]
    assert [record.attempt_no for record in records] == [1, 2, 3]


def test_transient_errors_give_up_after_three_retries():
    client = ScriptedClient([TransientLLMError("SERVER_ERROR")] * 4)
    report, records, sleeps = run(client, reviews(2))
    assert len(client.calls) == 1 + service.MAX_TRANSIENT_RETRIES
    assert sleeps == [1.0, 2.0, 4.0]
    assert [outcome.status for outcome in report.outcomes] == ["failed", "failed"]
    assert all(outcome.error_code == "SERVER_ERROR" for outcome in report.outcomes)
    assert all(outcome.ad_probability is None for outcome in report.outcomes)
    assert not report.aborted


def test_permanent_error_is_not_retried_and_stops_the_remaining_batches():
    client = ScriptedClient([PermanentLLMError("HTTP_401")])
    report, records, sleeps = run(client, reviews(25))
    assert len(client.calls) == 1
    assert sleeps == []
    assert report.aborted
    assert [outcome.status for outcome in report.outcomes] == ["failed"] * 10
    assert all(outcome.error_code == "HTTP_401" for outcome in report.outcomes)
    assert report.not_run == list(range(11, 26))
    assert [record.status for record in records] == ["api_error"]


def test_one_failed_batch_does_not_stop_the_next_batch():
    client = ScriptedClient([TransientLLMError("TIMEOUT")] * 4 + [ok_result([(11, 0.5)])])
    report, _, _ = run(client, reviews(11))
    statuses = [outcome.status for outcome in report.outcomes]
    assert statuses == ["failed"] * 10 + ["ok"]


def test_prompt_sends_only_review_id_title_and_text_and_never_author_or_variant():
    client = EchoClient()
    run(client, [ReviewInput(1, None, "본문만"), ReviewInput(2, "제목만", None)])
    items = prompt_items(client.calls[0]["user_prompt"])
    assert items == [
        {"review_id": 1, "title": None, "review_text": "본문만"},
        {"review_id": 2, "title": "제목만", "review_text": None},
    ]
    sent = client.calls[0]["user_prompt"] + SYSTEM_PROMPT
    assert "author" not in sent and "variant" not in sent


def test_batch_size_must_be_positive():
    with pytest.raises(ValueError):
        judge_reviews(EchoClient(), "m", reviews(1), batch_size=0)


def test_assumed_constants_are_the_documented_ones():
    # 가정 값(SQ-9 미정). 바꾸면 이 테스트와 문서를 함께 고친다.
    assert service.BATCH_SIZE == 10
    assert service.MAX_TRANSIENT_RETRIES == 3
    assert service.MAX_VALIDATION_RETRIES == 2
    assert results_text([(1, 0.5)])
