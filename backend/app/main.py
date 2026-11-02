from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import REQUEST_ID_HEADER, RequestIdMiddleware
from app.routers import dashboard, demo, pipeline, read

settings = get_settings()

setup_logging()  # JSON 로그: 표준 출력과 backend/logs/ (spec.md 7.3)

app = FastAPI(title="한국후지필름형 정기 설문 폐루프 에이전트")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=[REQUEST_ID_HEADER],
)
# 가장 바깥에 둔다: 모든 응답(CORS 응답 포함)에 request_id가 붙는다.
app.add_middleware(RequestIdMiddleware)
register_error_handlers(app)

app.include_router(pipeline.router)
app.include_router(demo.router)
app.include_router(read.router)
app.include_router(dashboard.router)
