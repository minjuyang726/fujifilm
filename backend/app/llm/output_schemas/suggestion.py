"""호출 B 출력의 JSON 스키마(suggest-v4 액션 카드). 영역 존재·중복·숫자 금지·자리표시자 규칙은 card_validators.py가 검사한다."""

from app.llm.prompts.suggestion import DELIVERABLE_KINDS

SCHEMA_NAME = "action_cards"

SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "area_code": {"type": "string"},
                    "priority_sentence": {"type": "string"},
                    "deliverable_kind": {"type": "string", "enum": list(DELIVERABLE_KINDS)},
                    "deliverable_text": {"type": "string"},
                },
                "required": ["area_code", "priority_sentence", "deliverable_kind", "deliverable_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}
