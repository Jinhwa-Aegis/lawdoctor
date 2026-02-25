"""피드백 API 엔드포인트"""

from typing import Optional
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from middleware.auth import get_current_user
from models.user import User
from models.feedback import Feedback, FeedbackType, FeedbackReason

logger = structlog.get_logger()

router = APIRouter()


# === Request / Response 스키마 ===

class FeedbackRequest(BaseModel):
    message_id: int
    feedback_type: FeedbackType
    reason: Optional[FeedbackReason] = None
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    message_id: int
    feedback_type: str
    reason: Optional[str] = None
    comment: Optional[str] = None
    created_at: str


class FeedbackStats(BaseModel):
    total: int
    positive: int
    negative: int
    positive_ratio: float
    top_negative_reasons: list[dict]


# === 엔드포인트 ===

@router.post("", response_model=FeedbackResponse)
async def create_feedback(
    req: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """피드백 등록 (👍/👎)"""
    # 중복 피드백 확인
    existing = await db.execute(
        select(Feedback).where(
            Feedback.message_id == req.message_id,
            Feedback.user_id == user.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="이미 피드백을 제출했습니다.")

    feedback = Feedback(
        message_id=req.message_id,
        user_id=user.id,
        feedback_type=req.feedback_type,
        reason=req.reason,
        comment=req.comment,
    )
    db.add(feedback)
    await db.flush()

    logger.info(
        "피드백 등록",
        user_id=user.id,
        message_id=req.message_id,
        feedback_type=req.feedback_type.value,
    )

    return FeedbackResponse(
        id=feedback.id,
        message_id=feedback.message_id,
        feedback_type=feedback.feedback_type.value,
        reason=feedback.reason.value if feedback.reason else None,
        comment=feedback.comment,
        created_at=feedback.created_at.isoformat(),
    )


@router.get("/stats", response_model=FeedbackStats)
async def get_feedback_stats(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """피드백 통계 조회"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 전체 피드백 수
    total_result = await db.execute(
        select(func.count(Feedback.id)).where(Feedback.created_at >= since)
    )
    total = total_result.scalar() or 0

    # 긍정 피드백 수
    positive_result = await db.execute(
        select(func.count(Feedback.id)).where(
            and_(
                Feedback.created_at >= since,
                Feedback.feedback_type == FeedbackType.POSITIVE,
            )
        )
    )
    positive = positive_result.scalar() or 0
    negative = total - positive

    # 부정 피드백 사유 Top 5
    reason_result = await db.execute(
        select(Feedback.reason, func.count(Feedback.id).label("cnt"))
        .where(
            and_(
                Feedback.created_at >= since,
                Feedback.feedback_type == FeedbackType.NEGATIVE,
                Feedback.reason.isnot(None),
            )
        )
        .group_by(Feedback.reason)
        .order_by(desc("cnt"))
        .limit(5)
    )
    top_reasons = [
        {"reason": row.reason.value if row.reason else "기타", "count": row.cnt}
        for row in reason_result.all()
    ]

    return FeedbackStats(
        total=total,
        positive=positive,
        negative=negative,
        positive_ratio=round(positive / total * 100, 1) if total > 0 else 0.0,
        top_negative_reasons=top_reasons,
    )
