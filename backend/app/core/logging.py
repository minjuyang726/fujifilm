"""JSON 로그(spec.md 7.3). 한 줄에 JSON 하나이고 표준 출력과 backend/logs/에 남긴다.

로그에 남기지 않는 것(7.4): 비밀 값, 리뷰의 title·review_text·author, 설문 응답 값, LLM 요청·응답 원문.
그래서 요청 본문과 쿼리 문자열, 예외 메시지는 기록하지 않는다. 예외는 종류와 위치(파일·줄·함수)만 남긴다.
"""

import json
import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG_DIR = BACKEND_DIR / "logs"
# 보존 기간과 회전은 정해지지 않았다(spec.md SQ-16). 기본안(설계 제안): 일 단위 파일, 7일(가정, 근거 없음) 보관.
RETENTION_DAYS = 7
LOG_FILE_NAME = "app.log"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED = {"fields", "event"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "request_id": (getattr(record, "fields", None) or {}).get("request_id") or request_id_var.get(),
            "event": getattr(record, "event", None) or record.getMessage(),
        }
        for key, value in (getattr(record, "fields", None) or {}).items():
            payload.setdefault(key, value)
        if getattr(record, "event", None):
            message = record.getMessage()
            if message != payload["event"]:
                payload["message"] = message
        return json.dumps(payload, ensure_ascii=False, default=str)


def exception_location(exc: BaseException, depth: int = 5) -> list[str]:
    """예외 메시지 대신 위치만 남긴다. 메시지에는 SQL 문장이나 접속 정보가 들어갈 수 있다."""
    frames = traceback.extract_tb(exc.__traceback__)[-depth:]
    return [f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in frames]


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> Path:
    """루트 로거에 JSON 핸들러(표준 출력, 파일)를 단다. 여러 번 불러도 핸들러가 늘지 않는다."""
    directory = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    directory.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_fujifilm_json", False):
            root.removeHandler(handler)
            handler.close()
    formatter = JsonFormatter()
    stream = logging.StreamHandler(sys.stdout)
    file_handler = TimedRotatingFileHandler(
        directory / LOG_FILE_NAME, when="midnight", backupCount=RETENTION_DAYS, encoding="utf-8"
    )
    for handler in (stream, file_handler):
        handler.setFormatter(formatter)
        handler._fujifilm_json = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level)
    return directory / LOG_FILE_NAME


def log_event(logger: logging.Logger, level: int, event: str, **fields) -> None:
    logger.log(level, event, extra={"event": event, "fields": fields})
