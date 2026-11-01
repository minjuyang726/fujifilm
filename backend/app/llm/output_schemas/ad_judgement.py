"""호출 A 출력의 JSON 스키마(spec.md 6.2절). 범위(0~1)와 개수는 validators.py가 검사한다."""

SCHEMA_NAME = "ad_judgement"

AD_JUDGEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "review_id": {"type": "integer"},
                    "ad_probability": {"type": "number"},
                },
                "required": ["review_id", "ad_probability"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}
