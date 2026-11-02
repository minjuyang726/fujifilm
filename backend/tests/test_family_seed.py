"""제품군 시드. 임시 SQLite만 쓴다."""

from sqlalchemy import func, select

from app.models import Product, ProductFamily
from app.services.family_seed import FAMILIES, PRODUCT_TO_FAMILY, seed_families


def add_products(session, extra=()):
    for name in [*PRODUCT_TO_FAMILY, *extra]:
        session.add(Product(product_name=name))
    session.commit()


def test_mapping_table_matches_g1_one_plus_two():
    assert FAMILIES == ("일회용 카메라", "인스탁스 즉석카메라")
    values = list(PRODUCT_TO_FAMILY.values())
    assert values.count("일회용 카메라") == 1 and values.count("인스탁스 즉석카메라") == 2
    assert set(values) == set(FAMILIES)


def test_seed_inserts_families_and_fills_family_id(session):
    add_products(session)
    result = seed_families(session)
    session.commit()
    assert result["families_to_insert"] == 2 and result["products_updated"] == 3 and result["products_unmapped"] == 0
    ids = {f.name: f.family_id for f in session.scalars(select(ProductFamily))}
    assert ids == {"일회용 카메라": 1, "인스탁스 즉석카메라": 2}
    for name, family in PRODUCT_TO_FAMILY.items():
        assert session.get(Product, name).family_id == ids[family]


def test_seed_twice_changes_nothing(session):
    add_products(session)
    seed_families(session)
    session.commit()
    second = seed_families(session)
    session.commit()
    assert second["families_to_insert"] == 0 and second["products_updated"] == 0 and second["products_already_set"] == 3
    assert session.scalar(select(func.count()).select_from(ProductFamily)) == 2


def test_unmapped_product_is_left_null_and_other_value_is_not_overwritten(session):
    add_products(session, extra=["매핑표에 없는 상품"])
    seed_families(session)
    session.commit()
    assert session.get(Product, "매핑표에 없는 상품").family_id is None
    name = next(iter(PRODUCT_TO_FAMILY))
    product = session.get(Product, name)
    other = 2 if product.family_id == 1 else 1
    product.family_id = other
    session.commit()
    result = seed_families(session)
    session.commit()
    assert result["products_conflict"] == 1 and result["products_unmapped"] == 1
    assert session.get(Product, name).family_id == other


def test_dry_run_writes_nothing_and_reports_counts(session):
    add_products(session, extra=["다른 상품"])
    result = seed_families(session, dry_run=True)
    session.rollback()
    assert result == {
        "families_to_insert": 2,
        "families_total": 2,
        "products_in_db": 4,
        "products_mapped": 3,
        "products_unmapped": 1,
        "mapping_names_not_in_db": 0,
    }
    assert session.scalar(select(func.count()).select_from(ProductFamily)) == 0
    assert all(p.family_id is None for p in session.scalars(select(Product)))
