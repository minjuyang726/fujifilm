"""설정 객체가 비밀 값을 출력에 내보내지 않는지 확인한다. 값은 모두 가짜다."""

from app.config import get_settings

FAKE_KEY = "sk-fake-key-for-repr-test-0000"
FAKE_DB = "postgresql://fake_user:fake_password@fake-host:5432/fake_db"


def test_settings_repr_and_str_never_contain_the_key_or_database_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("DATABASE_URL", FAKE_DB)
    monkeypatch.setenv("OPENAI_MODEL_AD", "some-model-name")

    settings = get_settings()

    # 값은 정상적으로 읽힌다 (숨기는 것은 출력뿐이다)
    assert settings.openai_api_key == FAKE_KEY
    assert settings.database_url == FAKE_DB
    for text in (repr(settings), str(settings), f"{settings}", f"{settings!r}"):
        assert FAKE_KEY not in text
        assert "fake_password" not in text
        assert "fake-host" not in text


def test_settings_repr_still_shows_the_non_secret_fields(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL_AD", "some-model-name")
    text = repr(get_settings())
    assert "some-model-name" in text
    assert "ad_judgement_max_items" in text
