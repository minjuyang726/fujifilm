"""오류 응답 형식(spec.md 7.1). 모든 오류 응답은 {"error": {code, message, details?, request_id}} 이다.

- 500 응답에는 스택 추적이나 DB 문장을 담지 않는다. 로그에는 예외 종류와 위치만 남긴다.
- 업무 규칙 오류는 HTTPException(detail={"code": ..., "message": ...})로 낸다. 그 코드를 그대로 쓴다.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import exception_location, log_event
from app.core.middleware import REQUEST_ID_HEADER

logger = logging.getLogger("app.error")

# 상태 코드별 기본 code와 message (7.1의 표). 표에 없는 405 등은 아래 기본값을 쓴다(구현에서 정함).
DEFAULTS = {
    400: ("BAD_REQUEST", "요청이 규칙에 맞지 않습니다."),
    404: ("NOT_FOUND", "요청한 대상을 찾을 수 없습니다."),
    405: ("METHOD_NOT_ALLOWED", "허용되지 않는 요청 방법입니다."),
    422: ("VALIDATION_ERROR", "요청 형식이 올바르지 않습니다."),
    500: ("INTERNAL_ERROR", "서버에서 오류가 발생했습니다."),
}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_response(request: Request, status_code: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    request_id = _request_id(request)
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    error["request_id"] = request_id
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    default_code, default_message = DEFAULTS.get(exc.status_code, ("ERROR", "요청을 처리하지 못했습니다."))
    code, message = default_code, default_message
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        code = str(exc.detail["code"])
        message = str(exc.detail.get("message") or default_message)
    return error_response(request, exc.status_code, code, message)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # 어떤 필드가 왜 틀렸는지만 담는다. 입력 값(input)은 담지 않는다.
    details = [
        {"field": ".".join(str(part) for part in error["loc"]), "reason": error["msg"]} for error in exc.errors()
    ]
    code, message = DEFAULTS[422]
    return error_response(request, 422, code, message, details)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log_event(
        logger,
        logging.ERROR,
        "unhandled_error",
        request_id=_request_id(request),
        error_type=type(exc).__name__,
        location=exception_location(exc),
    )
    code, message = DEFAULTS[500]
    return error_response(request, 500, code, message)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
