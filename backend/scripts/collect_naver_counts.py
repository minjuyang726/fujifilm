"""네이버 검색 결과 총 건수를 읽어 naver_search_count에 쌓는다(제한 구현 A안: 집계 숫자만, LLM 전송 없음).

backend 폴더에서 실행한다.
  python scripts/collect_naver_counts.py --query "질의1" --query "질의2" --dry-run   # 호출은 하지만 저장하지 않는다
  python scripts/collect_naver_counts.py --query "질의1" --query "질의2"             # 호출하고 저장한다 (먼저 alembic upgrade head)

- 질의 x (blog, cafearticle) 마다 네이버 API를 한 번 부른다. 재시도 없음, 시간 제한 10초, 질의는 최대 10개.
- 키는 backend/.env의 NAVER_API_CLIENT_ID, NAVER_API_CLIENT_SECRET에서만 읽는다. 실제 호출은 사용자 승인 후에 한다.
- 출력은 출처, 질의, 건수뿐이다. 글 내용은 읽지도 저장하지도 출력하지도 않는다.
"""

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy.orm import Session  # noqa: E402

import app.config  # noqa: E402,F401  (backend/.env를 읽는다)
from app.db import make_engine  # noqa: E402
from app.services.naver_counts import NaverError, collect_counts, make_fetch, save_counts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--query", action="append", required=True, help="검색어(여러 번 쓸 수 있다)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client_id = os.getenv("NAVER_API_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_API_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print("실패: backend/.env의 NAVER_API_CLIENT_ID, NAVER_API_CLIENT_SECRET을 채워 주세요.")
        return 1
    try:
        results = collect_counts(args.query, make_fetch(client_id, client_secret))
    except NaverError as error:
        print(f"실패: {error} (아무것도 저장하지 않았습니다)")
        return 1
    for source, query, total in results:
        print(f"{source}\t{query}\t{total}")
    if args.dry_run:
        print("저장하지 않았습니다(--dry-run).")
        return 0
    engine = make_engine()
    with Session(engine) as session:
        saved = save_counts(session, results)
    print(f"대상 DB: {engine.dialect.name} | 저장 {saved}행")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
