"""네이버 검색 API 제한 구현(A안, 결정 2026-11-03, 사용자 선택): 검색 결과 총 건수(total)만 읽어 저장한다.

- 응답에서 total 하나만 꺼내고 나머지(title, description, link, 블로거·카페 이름, 날짜)는 변수에 담지도 저장하지도 않는다.
  LLM에는 아무것도 보내지 않는다(이 모듈은 OpenAI를 쓰지 않는다).
- 호출은 질의 x 출처(blog, cafearticle)마다 한 번이다. 재시도하지 않고 시간 제한은 10초다. display=1, start=1, sort=sim.
- 하나라도 실패하면 아무것도 저장하지 않는다. 오류에는 상태 코드나 사유 코드만 담고 키와 응답 내용은 담지 않는다.
- 헤더 이름과 엔드포인트는 공식 문서(api.ncloud-docs.com NAVER API HUB 검색)를 따른다.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import NaverSearchCount

SOURCES = ("blog", "cafearticle")
ENDPOINT = "https://naverapihub.apigw.ntruss.com/search/v1/{source}"
TIMEOUT_SECONDS = 10
MAX_QUERIES = 10  # 한 번의 실행에서 질의 수 상한(호출 수 = 질의 수 x 2)


class NaverError(RuntimeError):
    """메시지에는 사유 코드만 쓴다."""


Fetch = Callable[[str, str], int]  # (source, query) -> total


def make_fetch(client_id: str, client_secret: str, *, opener=urllib.request.urlopen) -> Fetch:
    headers = {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}

    def fetch(source: str, query: str) -> int:
        params = urllib.parse.urlencode({"query": query, "display": 1, "start": 1, "sort": "sim"})
        request = urllib.request.Request(f"{ENDPOINT.format(source=source)}?{params}", headers=headers)
        try:
            with opener(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            raise NaverError(f"HTTP_{error.code}") from None
        except Exception:
            raise NaverError("REQUEST_FAILED") from None
        try:
            total = json.loads(body)["total"]
        except Exception:
            raise NaverError("BAD_RESPONSE") from None
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            raise NaverError("BAD_RESPONSE")
        return total

    return fetch


def collect_counts(queries: list[str], fetch: Fetch) -> list[tuple[str, str, int]]:
    """(source, query, total) 목록. 하나라도 실패하면 NaverError."""
    cleaned = [q.strip() for q in queries if q.strip()]
    if not cleaned:
        raise NaverError("NO_QUERY")
    if len(set(cleaned)) != len(cleaned):
        raise NaverError("DUPLICATE_QUERY")
    if len(cleaned) > MAX_QUERIES:
        raise NaverError("TOO_MANY_QUERIES")
    return [(source, query, fetch(source, query)) for query in cleaned for source in SOURCES]


def save_counts(session: Session, results: list[tuple[str, str, int]], *, now: datetime | None = None) -> int:
    when = now or datetime.now(timezone.utc)
    for source, query, total in results:
        session.add(NaverSearchCount(source=source, query=query, total=total, collected_at=when))
    session.commit()
    return len(results)
