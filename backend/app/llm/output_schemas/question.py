"""호출 C 출력의 JSON 스키마(spec.md 6.2절). 문항 길이·선택지 개수·숫자 금지는 question_validators.py가 검사한다."""

SCHEMA_NAME = "next_survey_questions"

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hypothesis_id": {"type": "integer"},
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": ["scale5", "single", "multi"]},
                    "options": {"type": ["array", "null"], "items": {"type": "string"}},
                },
                "required": ["hypothesis_id", "text", "type", "options"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}
