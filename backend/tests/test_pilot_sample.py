import datetime
import json
import sys

import pytest
from sqlalchemy import func, select

from app.models import Product, Review
from scripts import pilot_sample
from scripts.pilot_sample import DEFAULT_SEED, DEFAULT_SIZE, allocate_by_group, select_sample


def make_rows(counts):
    rows, review_id = [], 1
    for product_name, count in counts.items():
        for _ in range(count):
            rows.append((review_id, product_name))
            review_id += 1
    return rows


ROWS = make_rows({"A": 188, "B": 70, "C": 52})  # 합계 310


def test_defaults_are_the_documented_ones():
    assert DEFAULT_SEED == 20251101  # 가정
    assert DEFAULT_SIZE == 100  # 가정


def test_random_sample_has_the_requested_size_and_only_eligible_ids():
    ids, allocation = select_sample(ROWS, 100, DEFAULT_SEED)
    assert len(ids) == len(set(ids)) == 100
    assert set(ids) <= {review_id for review_id, _ in ROWS}
    assert ids == sorted(ids) and allocation == {}


def test_same_seed_gives_same_ids_and_other_seed_gives_other_ids():
    first, _ = select_sample(ROWS, 100, 1)
    again, _ = select_sample(ROWS, 100, 1)
    other, _ = select_sample(ROWS, 100, 2)
    assert first == again
    assert first != other


def test_input_order_does_not_change_the_result():
    forward, _ = select_sample(ROWS, 100, 5)
    backward, _ = select_sample(list(reversed(ROWS)), 100, 5)
    assert forward == backward


def test_stratified_sample_is_proportional_and_sums_to_size():
    ids, allocation = select_sample(ROWS, 100, DEFAULT_SEED, stratify="product")
    assert sum(allocation.values()) == 100 == len(ids)
    # 100 * 188/310 = 60.65, 100 * 70/310 = 22.58, 100 * 52/310 = 16.77. 내림하면 60+22+16=98이고
    # 남은 2는 소수 부분이 큰 순서(C 0.77, A 0.65)로 준다.
    assert allocation == {"A": 61, "B": 22, "C": 17}
    by_product = {name: 0 for name in allocation}
    for review_id, product_name in ROWS:
        if review_id in set(ids):
            by_product[product_name] += 1
    assert by_product == allocation


def test_stratified_sample_is_reproducible():
    first = select_sample(ROWS, 100, 9, stratify="product")
    again = select_sample(ROWS, 100, 9, stratify="product")
    assert first == again


def test_allocation_never_exceeds_group_size_and_handles_small_groups():
    allocation = allocate_by_group({"A": 1, "B": 1, "C": 98}, 10)
    assert sum(allocation.values()) == 10
    assert allocation["A"] <= 1 and allocation["B"] <= 1


def test_size_larger_than_population_returns_everyone():
    ids, _ = select_sample(make_rows({"A": 3}), 100, 1)
    assert ids == [1, 2, 3]


def test_invalid_options_are_rejected():
    with pytest.raises(ValueError):
        select_sample(ROWS, 10, 1, stratify="family")
    with pytest.raises(ValueError):
        select_sample(ROWS, -1, 1)


def test_script_reads_only_and_writes_ids_without_review_text(session, session_factory, db_engine, tmp_path, monkeypatch, capsys):
    session.add(Product(product_name="상품A"))
    session.flush()
    secret = "본문-비밀-파일에-쓰면-안-됨"
    for review_id in range(1, 11):
        session.add(
            Review(
                review_id=review_id, product_name="상품A", rating=5, date=datetime.date(2026, 1, 1),
                helpful_count=0, title=None if review_id <= 4 else "제목", review_text=secret if review_id % 2 else None,
            )
        )
    session.commit()
    before = session.scalar(select(func.count()).select_from(Review))

    out = tmp_path / "pilot.json"
    monkeypatch.setattr(pilot_sample, "make_engine", lambda: db_engine)
    monkeypatch.setattr(sys, "argv", ["pilot_sample.py", "--size", "3", "--out", str(out)])
    assert pilot_sample.main() == 0

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["seed"] == DEFAULT_SEED and saved["size"] == 3 and saved["stratify"] == "none"
    # 제목 또는 본문이 있는 리뷰: 1,3,5,7,9(본문) + 5~10(제목) -> 1,3,5,6,7,8,9,10 = 8건. 2,4는 둘 다 없음.
    assert saved["eligible_count"] == 8
    assert set(saved["review_ids"]) <= {1, 3, 5, 6, 7, 8, 9, 10}
    assert secret not in out.read_text(encoding="utf-8") and secret not in capsys.readouterr().out
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Review)) == before
