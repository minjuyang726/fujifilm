"""DB 연결. 운영은 Supabase(PostgreSQL), 테스트는 SQLite."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def normalize_url(url: str) -> str:
    """Supabase가 주는 postgresql:// 문자열을 psycopg 3 드라이버용으로 바꾼다."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str | None = None) -> Engine:
    """url이 없으면 환경 값 DATABASE_URL을 쓴다."""
    resolved = url or get_settings().database_url
    if not resolved:
        raise RuntimeError("DATABASE_URL이 없습니다. backend/.env에 넣어 주세요.")
    return create_engine(normalize_url(resolved), pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@lru_cache
def _default_session_factory() -> sessionmaker:
    return make_session_factory(make_engine())


def get_session() -> Iterator[Session]:
    """FastAPI 의존성. 요청마다 세션 하나를 열고 닫는다. 테스트는 이 함수를 대체한다."""
    session = _default_session_factory()()
    try:
        yield session
    finally:
        session.close()
