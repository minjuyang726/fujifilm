"""Supabase 연결 확인. backend 폴더에서 실행한다: python scripts/check_db.py

접속 문자열과 비밀번호는 출력하지 않는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import make_engine  # noqa: E402


def main() -> int:
    if not get_settings().database_url:
        print("실패: DATABASE_URL이 없습니다. backend/.env에 넣어 주세요.")
        return 1
    try:
        engine = make_engine()
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception as error:  # 오류 메시지에 접속 정보가 들어갈 수 있어 종류만 출력한다.
        print(f"실패: 연결하지 못했습니다 ({type(error).__name__}).")
        print("확인: DATABASE_URL이 session pooler 문자열인지, 비밀번호의 특수문자를 URL 인코딩했는지.")
        return 1
    print("성공: Supabase에 연결됐습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
