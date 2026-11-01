"""광고성 판정 파일럿용 표본 id를 뽑는다. DB에서 읽기만 하고 아무것도 쓰지 않는다.

backend 폴더에서 실행한다:
  python scripts/pilot_sample.py                      # 무작위 100건, seed 20251101
  python scripts/pilot_sample.py --stratify product   # 상품별로 나누어 비례 배분

- 대상: 제목 또는 본문이 있는 리뷰(실측 310건). 둘 다 없는 리뷰는 판정 대상이 아니다.
- 같은 seed와 같은 데이터면 항상 같은 id가 나온다.
- 제품군 목록이 아직 없어(G1) 층화는 상품(product_name) 단위로 한다.
- 결과 파일에는 review_id 목록과 설정만 있다. 리뷰 본문은 읽지도 쓰지도 않는다.
- 이름이 든 본문을 가려내는 일은 사람이 해야 한다. 이 스크립트는 하지 않는다.
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db import make_engine  # noqa: E402
from app.models import Review  # noqa: E402

DEFAULT_SEED = 20251101  # 가정: 노션 일정의 날짜를 쓴 임의의 고정 값
DEFAULT_SIZE = 100  # 가정: 노션 파일럿 규모
DEFAULT_OUT = BACKEND_DIR.parent / "database" / "data" / "pilot_sample_ids.json"


def allocate_by_group(group_sizes: dict[str, int], size: int) -> dict[str, int]:
    """그룹 크기에 비례해 size를 나눈다(최대 잔여법). 같은 입력이면 항상 같은 결과다."""
    total = sum(group_sizes.values())
    quotas = {name: size * count / total for name, count in group_sizes.items()}
    allocation = {name: int(quota) for name, quota in quotas.items()}
    leftover = size - sum(allocation.values())
    by_fraction = sorted(group_sizes, key=lambda name: (-(quotas[name] - allocation[name]), name))
    for name in by_fraction[:leftover]:
        allocation[name] += 1
    return allocation


def select_sample(
    rows: list[tuple[int, str]], size: int, seed: int, stratify: str = "none"
) -> tuple[list[int], dict[str, int]]:
    """rows는 (review_id, product_name) 목록이다. (정렬된 id 목록, 그룹별 건수)를 돌려준다."""
    if stratify not in ("none", "product"):
        raise ValueError("stratify는 none 또는 product여야 합니다.")
    if size < 0:
        raise ValueError("size는 0 이상이어야 합니다.")
    size = min(size, len(rows))
    rng = random.Random(seed)

    if stratify == "none":
        ids = sorted(review_id for review_id, _ in rows)
        picked = sorted(rng.sample(ids, size))
        return picked, {}

    groups: dict[str, list[int]] = defaultdict(list)
    for review_id, product_name in rows:
        groups[product_name].append(review_id)
    allocation = allocate_by_group({name: len(ids) for name, ids in groups.items()}, size)
    picked: list[int] = []
    for name in sorted(groups):
        picked.extend(rng.sample(sorted(groups[name]), allocation[name]))
    return sorted(picked), allocation


def main() -> int:
    parser = argparse.ArgumentParser(description="광고성 판정 파일럿 표본 id를 뽑는다.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--stratify", choices=("none", "product"), default="none")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    try:
        engine = make_engine()
    except RuntimeError as error:
        print(f"실패: {error}")
        return 1
    print(f"== 대상 DB: {engine.dialect.name} (읽기만 합니다)")
    try:
        with engine.connect() as conn:
            rows = [
                (row.review_id, row.product_name)
                for row in conn.execute(
                    select(Review.review_id, Review.product_name)
                    .where(Review.title.is_not(None) | Review.review_text.is_not(None))
                    .order_by(Review.review_id)
                )
            ]
    except Exception as error:  # 오류 메시지에 접속 정보가 들어갈 수 있어 종류만 출력한다.
        print(f"실패: DB에서 읽지 못했습니다 ({type(error).__name__}).")
        return 1

    if not rows:
        print("실패: 판정 대상 리뷰가 없습니다. 리뷰를 먼저 적재해 주세요.")
        return 1
    ids, allocation = select_sample(rows, args.size, args.seed, args.stratify)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "seed": args.seed,
                "size": len(ids),
                "stratify": args.stratify,
                "eligible_count": len(rows),
                "review_ids": ids,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"판정 대상 {len(rows)}건 중 {len(ids)}건을 뽑았습니다 (seed {args.seed}, 층화 {args.stratify}).")
    for name, count in sorted(allocation.items()):
        print(f"  상품 {name[:20]}…: {count}건")
    print(f"저장: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
