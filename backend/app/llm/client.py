"""OpenAI 호출만 한다. 프롬프트·검증·재시도는 이 파일 밖에 있다.

- 키는 환경 값 OPENAI_API_KEY에서만 읽고, 로그와 오류 메시지에 넣지 않는다.
- SDK의 자동 재시도는 끈다(max_retries=0). 재시도는 services/ad_judgement.py 한 곳에서만 한다.
- 오류는 재시도해도 되는 것(TransientLLMError)과 아닌 것(PermanentLLMError)으로만 나눠 올린다.
  원래 오류의 메시지에는 요청 내용이 들어갈 수 있어서 코드(종류)만 남긴다.
"""

from dataclasses import dataclass
from typing import Protocol

from app.config import get_settings

# SDK 호출 시간 제한(초). 가정이며 spec.md SQ-9가 정해지지 않았다.
REQUEST_TIMEOUT_SECONDS = 60.0


class LLMConfigError(RuntimeError):
    """키나 모델 이름 같은 설정이 없다."""


class ModelNotConfigured(LLMConfigError):
    """모델 이름(OPENAI_MODEL_AD)이 없다."""


class SuggestModelNotConfigured(LLMConfigError):
    """액션 제안 서술(호출 B)의 모델 이름(OPENAI_MODEL_SUGGEST)이 없다."""


class LLMCallError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class TransientLLMError(LLMCallError):
    """네트워크 오류, 시간 초과, 429, 5xx. 대기 후 다시 시도할 수 있다."""


class PermanentLLMError(LLMCallError):
    """인증 오류나 잘못된 요청처럼 다시 시도해도 소용없는 오류."""


@dataclass(frozen=True)
class LLMResult:
    text: str | None  # 모델이 돌려준 JSON 문자열. 거절 등으로 내용이 없으면 None
    input_tokens: int | None
    output_tokens: int | None


class LLMClient(Protocol):
    def complete_json(
        self, *, model: str, system_prompt: str, user_prompt: str, schema_name: str, json_schema: dict
    ) -> LLMResult: ...


def get_ad_model_name() -> str:
    """광고성 판정에 쓸 모델 이름. 코드에 쓰지 않고 환경 값 OPENAI_MODEL_AD에서만 읽는다."""
    model = get_settings().openai_model_ad
    if not model:
        raise ModelNotConfigured("OPENAI_MODEL_AD가 설정되지 않았습니다. backend/.env에 모델 이름을 넣어 주세요.")
    return model


class OpenAIClient:
    def __init__(self, api_key: str | None = None, *, sdk_client=None, timeout: float = REQUEST_TIMEOUT_SECONDS):
        if sdk_client is None:
            key = api_key or get_settings().openai_api_key
            if not key:
                raise LLMConfigError("OPENAI_API_KEY가 설정되지 않았습니다. backend/.env에 넣어 주세요.")
            from openai import OpenAI

            sdk_client = OpenAI(api_key=key, timeout=timeout, max_retries=0)
        self._sdk = sdk_client

    def complete_json(
        self, *, model: str, system_prompt: str, user_prompt: str, schema_name: str, json_schema: dict
    ) -> LLMResult:
        import openai

        try:
            response = self._sdk.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": json_schema, "strict": True},
                },
            )
        except openai.APITimeoutError:
            raise TransientLLMError("TIMEOUT") from None
        except openai.APIConnectionError:
            raise TransientLLMError("CONNECTION_ERROR") from None
        except openai.RateLimitError:
            raise TransientLLMError("RATE_LIMIT") from None
        except openai.APIStatusError as error:
            status = getattr(error, "status_code", 0) or 0
            if status >= 500:
                raise TransientLLMError("SERVER_ERROR") from None
            raise PermanentLLMError(f"HTTP_{status}") from None
        except openai.OpenAIError:
            raise PermanentLLMError("OPENAI_ERROR") from None

        choices = getattr(response, "choices", None) or []
        text = choices[0].message.content if choices else None
        usage = getattr(response, "usage", None)
        return LLMResult(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )


def build_default_client() -> OpenAIClient:
    """기본 클라이언트. OPENAI_API_KEY가 없으면 LLMConfigError를 낸다."""
    return OpenAIClient()


def get_suggest_model_name() -> str:
    """액션 제안 서술(호출 B)에 쓸 모델 이름. 환경 값 OPENAI_MODEL_SUGGEST에서만 읽는다."""
    model = get_settings().openai_model_suggest
    if not model:
        raise SuggestModelNotConfigured("OPENAI_MODEL_SUGGEST가 설정되지 않았습니다. backend/.env에 모델 이름을 넣어 주세요.")
    return model
