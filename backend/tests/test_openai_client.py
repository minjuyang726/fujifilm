"""OpenAIClient의 오류 분류. 가짜 SDK를 쓰므로 네트워크와 키가 필요 없다."""

from types import SimpleNamespace

import httpx2
import openai
import pytest

from app.llm.client import (
    LLMConfigError,
    ModelNotConfigured,
    OpenAIClient,
    PermanentLLMError,
    TransientLLMError,
    build_default_client,
    get_ad_model_name,
)

REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
SECRET_IN_MESSAGE = "sk-this-must-never-appear-in-our-errors"


def status_error(cls, status):
    return cls(SECRET_IN_MESSAGE, response=httpx2.Response(status, request=REQUEST), body=None)


class FakeSDK:
    def __init__(self, result=None, error=None):
        self.calls = []
        self._result, self._error = result, error
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._result


def call(sdk):
    return OpenAIClient(sdk_client=sdk).complete_json(
        model="m", system_prompt="s", user_prompt="u", schema_name="n", json_schema={"type": "object"}
    )


@pytest.mark.parametrize(
    ("error", "expected_class", "expected_code"),
    [
        (openai.APITimeoutError(request=REQUEST), TransientLLMError, "TIMEOUT"),
        (openai.APIConnectionError(request=REQUEST), TransientLLMError, "CONNECTION_ERROR"),
        (status_error(openai.RateLimitError, 429), TransientLLMError, "RATE_LIMIT"),
        (status_error(openai.InternalServerError, 500), TransientLLMError, "SERVER_ERROR"),
        (status_error(openai.InternalServerError, 503), TransientLLMError, "SERVER_ERROR"),
        (status_error(openai.AuthenticationError, 401), PermanentLLMError, "HTTP_401"),
        (status_error(openai.BadRequestError, 400), PermanentLLMError, "HTTP_400"),
    ],
)
def test_sdk_errors_are_classified_and_carry_only_a_code(error, expected_class, expected_code):
    with pytest.raises(expected_class) as caught:
        call(FakeSDK(error=error))
    assert caught.value.code == expected_code
    assert SECRET_IN_MESSAGE not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__


def test_success_returns_text_and_token_counts_and_uses_structured_output():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"results": []}'))],
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
    )
    sdk = FakeSDK(result=response)
    result = call(sdk)
    assert (result.text, result.input_tokens, result.output_tokens) == ('{"results": []}', 7, 3)
    kwargs = sdk.calls[0]
    assert kwargs["model"] == "m"
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["strict"] is True
    assert [message["role"] for message in kwargs["messages"]] == ["system", "user"]
    assert "temperature" not in kwargs  # 무작위성 값은 SQ-9가 정해질 때까지 정하지 않는다


def test_empty_content_becomes_none_text():
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))], usage=None)
    result = call(FakeSDK(result=response))
    assert result.text is None and result.input_tokens is None


def test_default_client_without_api_key_raises_a_clear_error():
    with pytest.raises(LLMConfigError) as caught:
        build_default_client()
    assert "OPENAI_API_KEY" in str(caught.value)


def test_default_client_with_key_builds_without_calling_the_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key-0000000000")
    assert isinstance(build_default_client(), OpenAIClient)


def test_model_name_comes_only_from_the_environment(monkeypatch):
    with pytest.raises(ModelNotConfigured) as caught:
        get_ad_model_name()
    assert "OPENAI_MODEL_AD" in str(caught.value)
    monkeypatch.setenv("OPENAI_MODEL_AD", "some-model-name")
    assert get_ad_model_name() == "some-model-name"
