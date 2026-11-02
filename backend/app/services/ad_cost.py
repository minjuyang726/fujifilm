"""광고성 판정에 보낼 글의 글자 수를 센다. 본문은 가져오지 않고 길이만 읽는다.

비용 가드(app/llm/cost.py)와 읽기 전용 스크립트가 같은 계산을 쓰도록 한 곳에 둔다.
"""

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Review


def char_counts_to_send(session: Session, review_ids: Iterable[int]) -> list[int]:
    """review_ids 중 LLM에 보낼 글(제목 또는 본문이 있는 글)마다 (제목 글자 수 + 본문 글자 수)를 돌려준다.

    제목과 본문이 모두 없는 글은 보내지 않으므로 뺀다(FR-1.11).
    """
    rows = session.execute(
        select(Review.review_id, func.length(Review.title), func.length(Review.review_text))
        .where(Review.review_id.in_(list(review_ids)))
        .order_by(Review.review_id)
    ).all()
    return [
        (title_len or 0) + (text_len or 0)
        for _review_id, title_len, text_len in rows
        if not (title_len is None and text_len is None)
    ]
