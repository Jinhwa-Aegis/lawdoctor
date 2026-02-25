"""피드백 모델"""

import enum
from datetime import datetime

from sqlalchemy import String, Text, Enum, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class FeedbackType(str, enum.Enum):
    POSITIVE = "positive"  # 👍
    NEGATIVE = "negative"  # 👎


class FeedbackReason(str, enum.Enum):
    INACCURATE = "inaccurate"           # 부정확
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # 근거 부족
    IRRELEVANT = "irrelevant"           # 관련 없는 답변
    HELPFUL = "helpful"                 # 도움됨
    OTHER = "other"                     # 기타


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType), nullable=False
    )
    reason: Mapped[FeedbackReason | None] = mapped_column(
        Enum(FeedbackReason), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
