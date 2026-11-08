"""법무주치의 — FastAPI 앱 진입점"""

from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.chat import router as chat_router
from api.review import router as review_router
from api.feedback import router as feedback_router
from api.admin import router as admin_router
from api.security import router as security_router
from sqlalchemy import text

from db.database import engine, Base, SCHEMA_PATCHES
from models import Document  # noqa: F401 — Base.metadata에 등록
from core.scheduler import start_scheduler, shutdown_scheduler
from middleware.auth import get_current_user
from middleware.ip_filter import IPFilterMiddleware

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(ensure_ascii=False),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    logger.info("법무주치의 서비스 시작", env=settings.app_env)
    # DB 테이블 생성 (개발 환경)
    if settings.app_env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("개발 환경: 테이블 자동 생성 완료")
    # create_all은 기존 테이블에 컬럼을 추가하지 않으므로 신규 컬럼을 보정한다 (모든 환경, 멱등)
    for stmt in SCHEMA_PATCHES:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception as exc:
            logger.error("스키마 보정 실패 — db/migrations 수동 적용 필요", sql=stmt, error=str(exc))
    start_scheduler()
    yield
    shutdown_scheduler()
    await engine.dispose()
    logger.info("법무주치의 서비스 종료")


app = FastAPI(
    title="법무주치의 API",
    description="AI 기반 사내 법률 자문 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IP 제한 미들웨어
app.add_middleware(IPFilterMiddleware)

# 라우터 등록
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])
app.include_router(review_router, prefix="/api/review", tags=["review"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(security_router, prefix="/api/security", tags=["security"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "법무주치의"}


@app.get("/api/auth/me")
async def get_me(user=Depends(get_current_user)):
    """현재 사용자 정보 반환"""
    return {
        "id": user.id,
        "name": user.display_name,
        "role": user.role.value,
    }
