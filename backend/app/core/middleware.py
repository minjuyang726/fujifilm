"""요청마다 request_id를 붙이고 요청 한 건을 한 줄로 기록한다.

- request_id는 서버가 새로 만든다(uuid4). 요청 헤더로 들어온 값은 믿지 않는다(로그 주입 방지).
- 응답 헤더 X-Request-ID와 오류 본문 error.request_id에 같은 값을 쓴다.
- 기록하는 것은 메서드, 경로, 상태 코드, 걸린 시간뿐이다. 쿼리 문자열과 본문은 남기지 않는다(spec.md 7.4).
"""

import logging
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import log_event, request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger("app.request")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status_holder = {"status": None}

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((REQUEST_ID_HEADER.lower().encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        except BaseException:
            # 처리되지 않은 예외는 바깥의 오류 처리기가 500을 낸다.
            status_holder["status"] = status_holder["status"] or 500
            raise
        finally:
            log_event(
                logger,
                logging.INFO,
                "request",
                method=scope["method"],
                path=scope["path"],
                status=status_holder["status"],
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            request_id_var.reset(token)
