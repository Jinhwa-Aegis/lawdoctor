"""역할 기반 인증 — 간이 인증 (MVP)"""

from typing import Optional

import structlog
from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_db
from models.user import User, UserRole

logger = structlog.get_logger()


async def _ensure_dev_user(db: AsyncSession) -> User:
    """개발 환경 전용: 기본 경영진 사용자가 없으면 자동 생성"""
    result = await db.execute(select(User).where(User.id == 1))
    user = result.scalar_one_or_none()
    if user:
        return user

    dev_user = User(
        username="admin",
        display_name="개발용 관리자",
        role=UserRole.EXECUTIVE,
    )
    db.add(dev_user)
    await db.flush()
    logger.info("개발 환경: 기본 경영진 사용자 자동 생성", user_id=dev_user.id)
    return dev_user


async def get_current_user(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """현재 사용자를 헤더에서 식별 (MVP: 간이 인증)"""
    if not x_user_id:
        # 개발 환경: 헤더 없으면 기본 사용자 반환
        if settings.app_env == "development":
            return await _ensure_dev_user(db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자 인증이 필요합니다. X-User-Id 헤더를 설정해주세요.",
        )

    try:
        user_id = int(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="잘못된 사용자 ID입니다.",
        )

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()

    if not user:
        # 개발 환경: 사용자가 없으면 기본 사용자 반환
        if settings.app_env == "development":
            return await _ensure_dev_user(db)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="존재하지 않는 사용자입니다.",
        )
    return user


def require_role(required_role: UserRole):
    """특정 역할 이상만 접근 허용하는 의존성"""
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        # 개발 환경: 역할 제한 우회
        if settings.app_env == "development":
            return user
        # 경영진은 모든 권한
        if user.role == UserRole.EXECUTIVE:
            return user
        # 일반 직원은 STAFF 권한만
        if required_role == UserRole.EXECUTIVE and user.role != UserRole.EXECUTIVE:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="경영진 권한이 필요합니다.",
            )
        return user
    return role_checker
