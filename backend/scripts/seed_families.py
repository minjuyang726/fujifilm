"""제품군(product_family)을 넣고 product.family_id를 채운다. G1 결정(2026-11-02)의 시드다.

backend 폴더에서 실행한다.
  python scripts/seed_families.py --dry-run   # DB를 읽기만 하고 쓸 때의 건수를 보여 준다
  python scripts/seed_families.py             # DATABASE_URL이 가리키는 DB에 쓴다 (먼저 alembic upgrade head)

- 대응 근거와 표는 app/services/family_seed.py에 있다. 표에 없는 상품은 건드리지 않는다.
- 출력에는 건수만 있다.
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.services.family_seed import seed_families  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine = make_engine()
    print(f"대상 DB: {engine.dialect.name}" + (" (읽기만)" if args.dry_run else ""))
    with Session(engine) as session:
        if args.dry_run:
            print(seed_families(session, dry_run=True))
            return 0
        with session.begin():
            result = seed_families(session)
        print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
