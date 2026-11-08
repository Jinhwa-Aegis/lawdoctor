"""데이터베이스 연결 설정"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",
    pool_size=10,
    max_overflow=20,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# create_all이 처리하지 못하는 기존 테이블 컬럼 추가분 (멱등 SQL, 앱 시작 시 모든 환경에서 실행)
# 동일 내용이 db/migrations/ 에 SQL 파일로도 있다 (Alembic 도입 전 임시 방식).
SCHEMA_PATCHES: list[str] = [
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS answer_meta JSON",
]


async def get_db() -> AsyncSession:
    """DB 세션 의존성 주입"""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
