"""테스트용 가짜 LLM 클라이언트. 실제 OpenAI는 호출하지 않는다."""

import json

from app.llm.client import LLMResult

PROMPT_HEADER = "다음 후기들의 광고성 확률을 판정하라.\n"


def prompt_items(user_prompt: str) -> list[dict]:
    return json.loads(user_prompt.split("\n", 1)[1])


def prompt_ids(user_prompt: str) -> list[int]:
    return [item["review_id"] for item in prompt_items(user_prompt)]


def results_text(pairs) -> str:
    return json.dumps(
        {"results": [{"review_id": review_id, "ad_probability": probability} for review_id, probability in pairs]}
    )


def ok_result(pairs, input_tokens=11, output_tokens=7) -> LLMResult:
    return LLMResult(text=results_text(pairs), input_tokens=input_tokens, output_tokens=output_tokens)


class ScriptedClient:
    """미리 정해 둔 응답이나 예외를 순서대로 돌려준다."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def complete_json(self, *, model, system_prompt, user_prompt, schema_name, json_schema):
        self.calls.append({"model": model, "system_prompt": system_prompt, "user_prompt": user_prompt})
        if not self.script:
            raise AssertionError("준비한 응답이 모자랍니다")
        step = self.script.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    def ids_per_call(self) -> list[list[int]]:
        return [prompt_ids(call["user_prompt"]) for call in self.calls]


class EchoClient:
    """입력된 review_id마다 (id % 10) / 10 확률을 돌려준다. omit에 있는 id는 일부러 빼고 답한다."""

    def __init__(self, omit=()):
        self.omit = set(omit)
        self.calls: list[dict] = []

    def complete_json(self, *, model, system_prompt, user_prompt, schema_name, json_schema):
        self.calls.append({"model": model, "user_prompt": user_prompt})
        ids = [review_id for review_id in prompt_ids(user_prompt) if review_id not in self.omit]
        return ok_result([(review_id, (review_id % 10) / 10) for review_id in ids])
