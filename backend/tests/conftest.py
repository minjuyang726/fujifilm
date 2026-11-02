"""모든 테스트 공통 설정. 테스트는 Supabase와 OpenAI에 접속하지 않는다."""

import pytest
from sqlalchemy.orm import sessionmaker

import app.db as app_db
from app.db import make_engine
from app.models import Base


@pytest.fixture(autouse=True)
def isolate_from_real_services(monkeypatch):
    """backend/.env의 값이 있어도 테스트가 실제 DB나 OpenAI를 쓰지 않게 막는다."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_AD", raising=False)
    monkeypatch.delenv("AD_JUDGEMENT_MAX_ITEMS", raising=False)
    # 비용 가드: 테스트는 실제 단가를 쓰지 않는다. 단가는 시험용 값(실제 단가와 무관)을 넣고 한도는 기본값을 쓴다.
    monkeypatch.delenv("AD_JUDGEMENT_COST_LIMIT_USD", raising=False)
    monkeypatch.setenv("OPENAI_PRICE_INPUT_PER_M", "0.20")
    monkeypatch.setenv("OPENAI_PRICE_OUTPUT_PER_M", "1.20")
    app_db._default_session_factory.cache_clear()
    yield
    app_db._default_session_factory.cache_clear()


@pytest.fixture
def db_engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def session(session_factory):
    with session_factory() as db_session:
        yield db_session
