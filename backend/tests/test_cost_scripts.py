"""비용 가드의 글자 수 읽기와 보정 스크립트의 표본 복원. SQLite와 가짜 클라이언트만 쓴다."""

import datetime
import importlib.util
from pathlib import Path

import pytest

from app.models import Product, Review, Round
from app.services.ad_cost import char_counts_to_send
from app.services.ad_judgement_step import run_ad_judgement_step
from tests.fakes import EchoClient, ScriptedClient, ok_result

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "calibrate_cost.py"


def load_script():
    spec = importlib.util.spec_from_file_location("calibrate_cost_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seeded(session):
    session.add(Product(product_name="상품A"))
    session.add(Round(label="2026Q4"))
    session.flush()
    rows = [(1, "가나", "다라마"), (2, None, "abcde"), (3, "xy", None), (4, None, None), (5, "", None)]
    for review_id, title, text in rows:
        session.add(
            Review(
                review_id=review_id, product_name="상품A", rating=5, date=datetime.date(2026, 1, 1),
                variant="옵션", helpful_count=0, title=title, review_text=text,
            )
        )
    session.commit()
    return session


def test_char_counts_count_only_lengths_and_skip_reviews_with_neither_title_nor_text(seeded):
    # 1: 2+3, 2: 0+5, 3: 2+0, 4: 둘 다 없음(뺀다), 5: 빈 제목(보낸다, 0자)
    assert char_counts_to_send(seeded, [1, 2, 3, 4, 5]) == [5, 5, 2, 0]
    assert char_counts_to_send(seeded, [4]) == []
    assert char_counts_to_send(seeded, []) == []


def test_samples_are_rebuilt_from_a_clean_run(seeded):
    run = run_ad_judgement_step(
        seeded, round_id=1, family_id=None, client=EchoClient(), model_name="m", max_items=100,
        review_ids=[1, 2, 3, 4, 5], sleep=lambda _s: None,
    )
    samples = load_script().collect_samples(seeded, run.run_id)
    assert [(s.items, s.chars, s.input_tokens, s.output_tokens) for s in samples] == [(4, 12, 11, 7)]


def test_runs_with_retries_cannot_be_used(seeded):
    # 1번 항목이 빠진 응답 -> 같은 항목을 다시 요청하므로 호출이 2번이고 묶음은 1개다
    client = ScriptedClient([ok_result([(2, 0.2), (3, 0.3), (5, 0.5)]), ok_result([(1, 0.1)])])
    run = run_ad_judgement_step(
        seeded, round_id=1, family_id=None, client=client, model_name="m", max_items=100,
        review_ids=[1, 2, 3, 4, 5], sleep=lambda _s: None,
    )
    with pytest.raises(ValueError):
        load_script().collect_samples(seeded, run.run_id)


def test_a_run_with_no_calls_cannot_be_used(seeded):
    with pytest.raises(ValueError):
        load_script().collect_samples(seeded, 999)
