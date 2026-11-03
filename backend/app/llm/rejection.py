"""호출 B·C 시도마다 거부 사유를 코드 값만으로 적는다(llm_call_log.error_code, 스키마 변경 없음).

예: "dropped_other=2;missing_area=1;bad_placeholder=1". 스키마·JSON 문제는 그 코드(not_json, bad_schema)만 적는다.
리뷰 본문과 모델 출력 본문은 기록하지 않는다. 거부가 없으면 None이다.
"""


def rejection_codes(problem: str | None, counters: dict, reasons: dict) -> str | None:
    if problem:
        return problem
    parts = [f"{key}={value}" for key, value in counters.items() if key.startswith("dropped_") and value]
    parts += [f"{key}={value}" for key, value in reasons.items()]
    return ";".join(parts) or None
