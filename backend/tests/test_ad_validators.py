import json

import pytest

from app.llm import validators as v
from app.llm.validators import validate_ad_judgement


def body(*pairs):
    return json.dumps({"results": [{"review_id": i, "ad_probability": p} for i, p in pairs]})


def test_normal_response_is_fully_valid():
    result = validate_ad_judgement(body((1, 0.0), (2, 1.0), (3, 0.5)), [1, 2, 3])
    assert result.fully_valid
    assert result.accepted == {1: 0.0, 2: 1.0, 3: 0.5}
    assert result.rejected == []


@pytest.mark.parametrize("raw", [None, "", "not json", "[1, 2]", "null"])
def test_unreadable_response_rejects_everything(raw):
    result = validate_ad_judgement(raw, [1, 2])
    assert result.accepted == {}
    assert result.rejected == [1, 2]
    assert result.problems & {v.NOT_JSON, v.BAD_SCHEMA}


@pytest.mark.parametrize(
    "raw",
    [
        '{"items": []}',
        '{"results": "x"}',
        '{"results": [], "extra": 1}',
    ],
)
def test_wrong_top_level_schema_rejects_everything(raw):
    result = validate_ad_judgement(raw, [1])
    assert v.BAD_SCHEMA in result.problems
    assert result.rejected == [1]


def test_length_mismatch_missing_id_is_rejected_for_retry():
    result = validate_ad_judgement(body((1, 0.1), (3, 0.3)), [1, 2, 3])
    assert v.LENGTH_MISMATCH in result.problems
    assert result.accepted == {1: 0.1, 3: 0.3}
    assert result.rejected == [2]


def test_extra_result_is_a_length_mismatch_but_valid_items_are_kept():
    result = validate_ad_judgement(body((1, 0.1), (2, 0.2), (9, 0.9)), [1, 2])
    assert v.LENGTH_MISMATCH in result.problems
    assert v.UNKNOWN_ID in result.problems
    assert result.accepted == {1: 0.1, 2: 0.2}
    assert result.rejected == []


def test_id_not_in_input_is_never_accepted():
    result = validate_ad_judgement(body((7, 0.5)), [1])
    assert v.UNKNOWN_ID in result.problems
    assert result.accepted == {}
    assert result.rejected == [1]


def test_duplicate_id_rejects_that_id_only():
    result = validate_ad_judgement(body((1, 0.1), (1, 0.9), (2, 0.2)), [1, 2])
    assert v.DUPLICATE_ID in result.problems
    assert result.accepted == {2: 0.2}
    assert result.rejected == [1]


@pytest.mark.parametrize("probability", [-0.01, 1.01, 5, -3])
def test_probability_outside_zero_to_one_is_rejected(probability):
    result = validate_ad_judgement(body((1, probability), (2, 0.4)), [1, 2])
    assert v.BAD_PROBABILITY in result.problems
    assert result.accepted == {2: 0.4}
    assert result.rejected == [1]


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_probability_is_rejected(token):
    raw = '{"results": [{"review_id": 1, "ad_probability": %s}]}' % token
    result = validate_ad_judgement(raw, [1])
    assert v.BAD_PROBABILITY in result.problems
    assert result.rejected == [1]


@pytest.mark.parametrize(
    "entry",
    [
        {"review_id": "1", "ad_probability": 0.1},
        {"review_id": 1.0, "ad_probability": 0.1},
        {"review_id": True, "ad_probability": 0.1},
        {"review_id": 1, "ad_probability": "0.1"},
        {"review_id": 1, "ad_probability": True},
        {"review_id": 1, "ad_probability": None},
        {"review_id": 1},
        {"review_id": 1, "ad_probability": 0.1, "reason": "x"},
    ],
)
def test_malformed_item_is_rejected(entry):
    result = validate_ad_judgement(json.dumps({"results": [entry]}), [1])
    assert v.BAD_ITEM in result.problems
    assert result.accepted == {}
    assert result.rejected == [1]


def test_problems_contain_codes_not_values():
    result = validate_ad_judgement(body((1, 99999.5)), [1])
    assert all(isinstance(problem, str) and "99999" not in problem for problem in result.problems)
