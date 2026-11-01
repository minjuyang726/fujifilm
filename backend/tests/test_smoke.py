from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import make_engine, normalize_url
from app.main import app


def test_docs_page_opens():
    client = TestClient(app)
    assert client.get("/docs").status_code == 200


def test_sqlite_engine_connects_without_supabase():
    engine = make_engine("sqlite://")
    with engine.connect() as conn:
        assert conn.execute(text("select 1")).scalar() == 1


def test_postgres_url_gets_psycopg_driver():
    assert normalize_url("postgresql://u:p@host:5432/db").startswith("postgresql+psycopg://")
    assert normalize_url("postgres://u:p@host:5432/db").startswith("postgresql+psycopg://")
