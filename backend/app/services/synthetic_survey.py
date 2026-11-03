"""합성 설문 문항과 합성 응답 생성기. DB와 네트워크를 모른다.

**임의 설정, 시연용, 성과로 쓰지 않음.** 아래 문항 문구, 선택지, 확률표는 모두 새로 정한 임의 값이다.
KOSSDA 자료의 문항 내용, 변수명, 라벨, 응답자 값을 가져오지 않았고(척도·유형 구조만 참고),
실제 리뷰나 광고성 판정 통계에서 값을 가져오거나 맞추지도 않았다. 이 값에서 나온 수치는 성과로 쓰지 않는다.

- 응답은 문항별로 독립 추출한다(문항 사이 상관 구조 없음).
- 같은 SEED면 같은 결과가 나온다(random.Random의 random()만 쓴다).
"""

import random
from datetime import date

SEED = 20261103  # 고정 상수. 값을 바꾸면 생성 결과가 모두 바뀐다.
RESPONSES_PER_ROUND = 100

# (label, period_start, period_end): spec.md SQ-6 결정(달력 분기)
ROUNDS = (
    ("2026-Q1", date(2026, 1, 1), date(2026, 3, 31)),
    ("2026-Q2", date(2026, 4, 1), date(2026, 6, 30)),
)

TYPES = ("scale5", "single", "multi")


def _options(*labels: str) -> list[dict]:
    return [{"code": str(index), "label": label} for index, label in enumerate(labels, start=1)]


# 문항 10개. 두 회차에 똑같이 들어간다. (code, text, type, options)
QUESTIONS = (
    ("q01", "카메라를 사용해 본 전반적인 만족도는 어떠셨나요?", "scale5",
     _options("매우 불만족", "불만족", "보통", "만족", "매우 만족")),
    ("q02", "사진 결과물에 얼마나 만족하셨나요?", "scale5",
     _options("매우 불만족", "불만족", "보통", "만족", "매우 만족")),
    ("q03", "사용하기는 쉬웠나요?", "scale5",
     _options("매우 어려웠다", "어려웠다", "보통이다", "쉬웠다", "매우 쉬웠다")),
    ("q04", "가격에 비해 가치가 있다고 느끼셨나요?", "scale5",
     _options("전혀 그렇지 않다", "그렇지 않다", "보통이다", "그렇다", "매우 그렇다")),
    ("q05", "다시 구매할 의향이 있으신가요?", "scale5",
     _options("전혀 없다", "별로 없다", "보통이다", "있다", "매우 있다")),
    ("q06", "주로 어떤 때에 사용하셨나요?", "single",
     _options("여행", "모임·행사", "선물", "일상 기록", "기타")),
    ("q07", "가장 불편했던 점은 무엇인가요?", "single",
     _options("필름·소모품 비용", "현상·인화 대기", "사용법 안내", "결과물 품질", "불편한 점 없음")),
    ("q08", "개선되었으면 하는 점을 모두 골라 주세요.", "multi",
     _options("필름·소모품 비용", "현상·인화 대기", "사용법 안내", "결과물 품질", "개선할 점 없음")),
    ("q09", "지인에게 추천한 적이 있으신가요?", "single",
     _options("예", "아니오")),
    ("q10", "얼마나 자주 사용하셨나요?", "single",
     _options("거의 안 썼다", "월 1회 미만", "월 1~3회", "주 1~2회", "거의 매일")),
)

# 다중선택에서 다른 선택지와 함께 고를 수 없는 선택지(문항 code -> 선택지 code)
EXCLUSIVE = {"q08": "5"}

# 선택지 확률표(임의 값, 시연용). 라벨 순서대로이고 합이 1이다. q08(multi)은 아래 MULTI_TABLES에 있다.
# 두 회차에서 의도적으로 다른 문항은 q01, q07, q09 세 개뿐이다.
_COMMON = {
    "q02": [0.03, 0.07, 0.20, 0.42, 0.28],
    "q03": [0.05, 0.12, 0.25, 0.38, 0.20],
    "q04": [0.08, 0.14, 0.28, 0.32, 0.18],
    "q05": [0.06, 0.10, 0.26, 0.34, 0.24],
    "q06": [0.30, 0.25, 0.15, 0.22, 0.08],
    "q10": [0.25, 0.30, 0.25, 0.15, 0.05],
}
PROBABILITY_TABLES = {
    "2026-Q1": {
        **_COMMON,
        "q01": [0.04, 0.08, 0.22, 0.40, 0.26],
        "q07": [0.20, 0.22, 0.12, 0.18, 0.28],
        "q09": [0.45, 0.55],
    },
    "2026-Q2": {
        **_COMMON,
        "q01": [0.03, 0.06, 0.17, 0.42, 0.32],  # 만족 쪽으로 이동
        "q07": [0.18, 0.34, 0.11, 0.16, 0.21],  # '현상·인화 대기' 비중 증가
        "q09": [0.55, 0.45],  # 추천 경험 '예' 증가
    },
}
# 다중선택: p_none = '개선할 점 없음'을 고를 확률, p_include = 나머지 선택지를 각각 고를 확률(독립).
# 아무것도 안 골라지면 p_include를 가중치로 하나를 고른다(최소 1개).
MULTI_TABLES = {
    "2026-Q1": {"q08": {"p_none": 0.20, "p_include": [0.35, 0.40, 0.25, 0.30]}},
    "2026-Q2": {"q08": {"p_none": 0.20, "p_include": [0.35, 0.40, 0.25, 0.30]}},
}

_LABELS = [label for label, _, _ in ROUNDS]


def question_definitions() -> list[dict]:
    return [{"code": code, "text": text, "type": kind, "options": options} for code, text, kind, options in QUESTIONS]


def _pick(rng: random.Random, probabilities: list[float]) -> int:
    """누적 확률로 하나를 고른다. 반환은 0부터의 위치."""
    u = rng.random()
    total = 0.0
    for index, p in enumerate(probabilities):
        total += p
        if u < total:
            return index
    return len(probabilities) - 1


def _pick_multi(rng: random.Random, table: dict, none_index: int) -> list[int]:
    if rng.random() < table["p_none"]:
        return [none_index]
    include = table["p_include"]
    chosen = [index for index, p in enumerate(include) if rng.random() < p]
    if not chosen:
        chosen = [_pick(rng, [p / sum(include) for p in include])]
    return chosen


def generate(seed: int = SEED) -> dict:
    """합성 설문 데이터 전체를 만든다. 문항 유형과 선택지는 QUESTIONS, 확률은 위 표를 쓴다."""
    rng = random.Random(seed)
    rounds = []
    for label, start, end in ROUNDS:
        responses = []
        for _ in range(RESPONSES_PER_ROUND):
            answers = {}
            for code, _text, kind, options in QUESTIONS:
                codes = [option["code"] for option in options]
                if kind == "multi":
                    table = MULTI_TABLES[label][code]
                    none_index = codes.index(EXCLUSIVE[code])
                    answers[code] = [codes[i] for i in sorted(_pick_multi(rng, table, none_index))]
                else:
                    answers[code] = [codes[_pick(rng, PROBABILITY_TABLES[label][code])]]
            responses.append(answers)
        rounds.append(
            {
                "label": label,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "questions": question_definitions(),
                "responses": responses,
            }
        )
    return {
        "synthetic": True,
        "note": "임의 설정, 시연용, 성과로 쓰지 않음",
        "seed": seed,
        "rounds": rounds,
    }


class DatasetError(ValueError):
    """합성 데이터가 규칙을 어길 때. 메시지에는 위치와 규칙만 쓴다."""


def validate_dataset(data: dict) -> None:
    """모든 값이 문항의 허용 값 안에 있는지, 회차당 건수와 다중선택 규칙을 지키는지 검사한다."""
    if data.get("synthetic") is not True:
        raise DatasetError("synthetic 표시가 참이 아닙니다")
    rounds = data.get("rounds")
    if not isinstance(rounds, list) or [r.get("label") for r in rounds] != _LABELS:
        raise DatasetError("회차 목록이 2026-Q1, 2026-Q2와 다릅니다")
    expected_questions = question_definitions()
    for round_data in rounds:
        label = round_data["label"]
        if round_data.get("questions") != expected_questions:
            raise DatasetError(f"{label}: 문항 정의가 코드의 정의와 다릅니다")
        responses = round_data.get("responses")
        if not isinstance(responses, list) or len(responses) != RESPONSES_PER_ROUND:
            raise DatasetError(f"{label}: 응답 수가 {RESPONSES_PER_ROUND}건이 아닙니다")
        for position, answers in enumerate(responses, start=1):
            if set(answers) != {q[0] for q in QUESTIONS}:
                raise DatasetError(f"{label} 응답 {position}: 문항 코드가 맞지 않습니다")
            for code, _text, kind, options in QUESTIONS:
                values = answers[code]
                allowed = {option["code"] for option in options}
                if not isinstance(values, list) or not values or len(set(values)) != len(values):
                    raise DatasetError(f"{label} 응답 {position} {code}: 값이 비었거나 중복입니다")
                if not set(values) <= allowed:
                    raise DatasetError(f"{label} 응답 {position} {code}: 허용 값 밖의 값이 있습니다")
                if kind != "multi" and len(values) != 1:
                    raise DatasetError(f"{label} 응답 {position} {code}: 단일 값이어야 합니다")
                if kind == "multi" and EXCLUSIVE[code] in values and len(values) > 1:
                    raise DatasetError(f"{label} 응답 {position} {code}: 배타 선택지와 다른 선택지를 함께 골랐습니다")
