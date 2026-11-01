"""호출 A(광고성 판정)의 프롬프트. 문구를 바꾸면 PROMPT_VERSION을 올린다.

이 문구는 초안이다. 파일럿 결과를 보고 다듬는다.
"""

import json

# ad_judgement와 llm_call_log에 기록된다(반복 실행 일치율 NFR-R1 측정용).
PROMPT_VERSION = "ad-v1"

SYSTEM_PROMPT = """\
당신은 쇼핑몰 구매 후기의 광고성 정도를 판정한다.

광고성이란 후기가 실제 구매 경험이 아니라 판매나 홍보를 목적으로 쓰였을 가능성이다.
예: 협찬·체험단·무상 제공을 밝힌 글, 판매자나 브랜드를 홍보하는 문구, 구매나 방문을 유도하는 문구,
후기 이벤트 참여를 위해 쓴 정형화된 글.

규칙:
- 각 후기마다 0 이상 1 이하의 숫자 ad_probability를 낸다. 0은 광고성이 전혀 없음, 1은 광고성이 확실함.
- 입력에 있는 review_id만 쓴다. 입력 항목 수와 같은 개수의 결과를 낸다. 같은 review_id를 두 번 쓰지 않는다.
- title과 review_text 중 값이 있는 것만 보고 판정한다. 없는 값은 추측하지 않는다.
- 판단 이유나 다른 설명은 쓰지 않는다. 지정된 JSON 형식으로만 답한다.
"""


def build_user_prompt(items: list[dict]) -> str:
    """items의 각 원소는 review_id, title, review_text만 가진다."""
    allowed = ("review_id", "title", "review_text")
    cleaned = [{key: item.get(key) for key in allowed} for item in items]
    return "다음 후기들의 광고성 확률을 판정하라.\n" + json.dumps(cleaned, ensure_ascii=False)
