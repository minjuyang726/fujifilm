"""제품군 시드(G1 결정, 2026-11-02: DR-6 제안 채택 = 일회용 카메라 1개 상품 + 인스탁스 즉석카메라 2개 상품).

- 제품군 이름은 spec.md 3.2절 product_family의 제안 이름이다.
- 상품 -> 제품군 대응은 상품명 자체가 근거다(상품명에 '일회용 카메라' / '인스탁스 ... 즉석카메라'가 적혀 있다).
  아래 표에 없는 상품은 건드리지 않는다(family_id는 NULL로 남는다). 추측으로 대응을 만들지 않는다.
- 이미 다른 값이 들어 있는 family_id는 덮어쓰지 않고 건수만 알린다.
- 여러 번 실행해도 결과가 같다.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, ProductFamily

FAMILIES = ("일회용 카메라", "인스탁스 즉석카메라")  # 이 순서로 family_id가 매겨진다(1, 2)

PRODUCT_TO_FAMILY = {
    "후지 QuickSnap 일회용 카메라 400/27": "일회용 카메라",
    "인스탁스 mini EVO 즉석카메라 FI019 풀패키지 세트": "인스탁스 즉석카메라",
    "인스탁스 즉석카메라 클레이화이트 + 가방 + 필름 10p x 2팩 + 스트랩 세트 MINI12": "인스탁스 즉석카메라",
}


def seed_families(session: Session, dry_run: bool = False) -> dict:
    """제품군을 넣고 상품의 family_id를 채운다. 건수만 돌려준다. 호출한 쪽이 commit한다.

    dry_run이면 DB에 쓰지 않고 쓸 때의 건수만 계산한다. product.family_id 열은 읽지 않는다(마이그레이션 전에도 읽을 수 있다).
    """
    existing = {row.name: row.family_id for row in session.execute(select(ProductFamily.name, ProductFamily.family_id))}
    missing = [name for name in FAMILIES if name not in existing]
    result = {"families_to_insert": len(missing), "families_total": len(FAMILIES)}
    if dry_run:
        names = set(session.scalars(select(Product.product_name)))
        result["products_in_db"] = len(names)
        result["products_mapped"] = len(names & PRODUCT_TO_FAMILY.keys())
        result["products_unmapped"] = len(names - PRODUCT_TO_FAMILY.keys())
        result["mapping_names_not_in_db"] = len(PRODUCT_TO_FAMILY.keys() - names)
        return result

    for name in missing:
        session.add(ProductFamily(name=name))
        session.flush()  # 순서대로 번호가 매겨지게 한다
    ids = {row.name: row.family_id for row in session.execute(select(ProductFamily.name, ProductFamily.family_id))}

    updated = already = conflict = 0
    for product in session.scalars(select(Product).where(Product.product_name.in_(list(PRODUCT_TO_FAMILY)))):
        wanted = ids[PRODUCT_TO_FAMILY[product.product_name]]
        if product.family_id is None:
            product.family_id = wanted
            updated += 1
        elif product.family_id == wanted:
            already += 1
        else:
            conflict += 1
    unmapped = session.scalar(
        select(func.count()).select_from(Product).where(~Product.product_name.in_(list(PRODUCT_TO_FAMILY)))
    )
    result.update(products_updated=updated, products_already_set=already, products_conflict=conflict, products_unmapped=unmapped)
    return result
