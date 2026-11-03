"""호출 B 출력의 JSON 스키마(spec.md 6.2절). 문장 길이·개수·row_id 존재는 suggestion_validators.py가 검사한다."""

SCHEMA_NAME = "action_suggestions"

SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence": {"type": "string"},
                    "row_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["sentence", "row_ids"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}
