"""호출 C 출력의 JSON 스키마(question-v4). 형식·선택지·항목은 모델이 쓰지 않는다: 스키마에 없는 키(type, options, items)는 막힌다.
문항 길이·양끝 라벨 규칙·숫자 금지는 question_validators.py가 검사한다."""

SCHEMA_NAME = "next_survey_question_texts"

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
                    "low_label": {"type": "string"},
                    "high_label": {"type": "string"},
                },
                "required": ["hypothesis_id", "text", "low_label", "high_label"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}
