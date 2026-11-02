"""합성 설문 생성기. DB와 네트워크를 쓰지 않는다."""

import copy
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

from app.services import synthetic_survey as gen

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "generate_synthetic_survey.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("generate_synthetic_survey", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_same_seed_gives_identical_bytes():
    script = _load_script()
    first = script.render(gen.generate())
    second = script.render(gen.generate())
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()
    assert first == second


def test_different_seed_gives_different_output():
    script = _load_script()
    assert script.render(gen.generate(1)) != script.render(gen.generate(2))


def test_script_writes_the_same_file_twice(tmp_path, monkeypatch):
    script = _load_script()
    out = tmp_path / "out.json"
    monkeypatch.setattr("sys.argv", ["generate_synthetic_survey.py", "--out", str(out)])
    assert script.main() == 0
    first = hashlib.sha256(out.read_bytes()).hexdigest()
    assert script.main() == 0
    assert hashlib.sha256(out.read_bytes()).hexdigest() == first


def test_one_hundred_responses_per_round_and_ten_questions_in_both_rounds():
    data = gen.generate()
    assert [r["label"] for r in data["rounds"]] == ["2026-Q1", "2026-Q2"]
    assert [len(r["responses"]) for r in data["rounds"]] == [100, 100]
    assert [len(r["questions"]) for r in data["rounds"]] == [10, 10]
    assert data["rounds"][0]["questions"] == data["rounds"][1]["questions"]
    assert data["synthetic"] is True and data["seed"] == gen.SEED


def test_every_value_is_within_the_allowed_options():
    data = gen.generate()
    gen.validate_dataset(data)  # 위반이 있으면 예외
    allowed = {q["code"]: {o["code"] for o in q["options"]} for q in data["rounds"][0]["questions"]}
    for round_data in data["rounds"]:
        for answers in round_data["responses"]:
            assert set(answers) == set(allowed)
            for code, values in answers.items():
                assert set(values) <= allowed[code]


def test_multi_rule_at_least_one_and_exclusive_option():
    data = gen.generate()
    seen_exclusive = seen_multiple = False
    for round_data in data["rounds"]:
        for answers in round_data["responses"]:
            values = answers["q08"]
            assert len(values) >= 1 and len(set(values)) == len(values)
            if "5" in values:
                assert values == ["5"]
                seen_exclusive = True
            if len(values) > 1:
                seen_multiple = True
    assert seen_exclusive and seen_multiple  # 규칙이 실제로 시험된다
    for code in ("q01", "q02", "q06", "q09"):
        assert all(len(a[code]) == 1 for r in data["rounds"] for a in r["responses"])


def test_types_and_option_format():
    for _code, _text, kind, options in gen.QUESTIONS:
        assert kind in gen.TYPES
        assert all(set(o) == {"code", "label"} and isinstance(o["code"], str) for o in options)
        assert [o["code"] for o in options] == [str(i) for i in range(1, len(options) + 1)]
    assert gen.QUESTIONS[7][2] == "multi" and gen.QUESTIONS[7][3][-1]["label"] == "개선할 점 없음"
    assert [q[2] for q in gen.QUESTIONS].count("scale5") == 5


def test_probability_tables_sum_to_one_and_rounds_differ_in_exactly_three_questions():
    for table in gen.PROBABILITY_TABLES.values():
        for code, probabilities in table.items():
            options = next(q[3] for q in gen.QUESTIONS if q[0] == code)
            assert len(probabilities) == len(options)
            assert sum(probabilities) == pytest.approx(1.0)
    q1, q2 = gen.PROBABILITY_TABLES["2026-Q1"], gen.PROBABILITY_TABLES["2026-Q2"]
    assert {c for c in q1 if q1[c] != q2[c]} == {"q01", "q07", "q09"}
    assert gen.MULTI_TABLES["2026-Q1"] == gen.MULTI_TABLES["2026-Q2"]


def _broken(good, mutate):
    bad = copy.deepcopy(good)
    mutate(bad)
    return bad


def test_validate_rejects_broken_data():
    good = gen.generate()
    cases = [
        _broken(good, lambda d: d["rounds"][0]["responses"][0].__setitem__("q01", ["9"])),
        _broken(good, lambda d: d["rounds"][0]["responses"][0].__setitem__("q08", [])),
        _broken(good, lambda d: d["rounds"][0]["responses"][0].__setitem__("q08", ["1", "5"])),
        _broken(good, lambda d: d["rounds"][1]["responses"].pop()),
        _broken(good, lambda d: d["rounds"][0]["responses"][0].__setitem__("q01", ["1", "2"])),
        _broken(good, lambda d: d.__setitem__("synthetic", False)),
    ]
    for bad in cases:
        with pytest.raises(gen.DatasetError):
            gen.validate_dataset(bad)


def test_file_content_is_json_and_marks_itself_synthetic():
    script = _load_script()
    parsed = json.loads(script.render(gen.generate()))
    assert parsed["synthetic"] is True and "시연용" in parsed["note"]


def test_distribution_is_not_degenerate():
    counts = Counter(a["q01"][0] for a in gen.generate()["rounds"][0]["responses"])
    assert len(counts) >= 3
