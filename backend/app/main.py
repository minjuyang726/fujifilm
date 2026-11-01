from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import pipeline

settings = get_settings()

app = FastAPI(title="한국후지필름형 정기 설문 폐루프 에이전트")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(pipeline.router)
