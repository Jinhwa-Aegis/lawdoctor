"""채팅 이력 모델"""

import enum
from datetime import datetime

from sqlalchemy import String, Text, Enum, DateTime, ForeignKey, Integer, func, JSON
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LegalCategory(str, enum.Enum):
    PRIVACY = "privacy"               # 개인정보보호
    CONTRACT = "contract"             # 계약 검토
    HOUSING = "housing"               # 공동주택관리법
    LITIGATION = "litigation"         # 소송·분쟁


class ServiceType(str, enum.Enum):
    LEGAL = "legal"
    SECURITY = "security"


class SecurityCategory(str, enum.Enum):
    NETWORK = "network"                 # 네트워크 보안
    SYSTEM = "system"                   # 시스템 보안
    APPLICATION = "application"         # 애플리케이션 보안
    CLOUD = "cloud"                     # 클라우드 보안
    COMPLIANCE = "compliance"           # ISMS-P/컴플라이언스
    DATA_PROTECTION = "data_protection" # 데이터 보호
    INCIDENT = "incident"               # 보안 사고 대응
    AUDIT = "audit"                     # 보안 감사


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="새 대화")
    category: Mapped[LegalCategory | None] = mapped_column(Enum(LegalCategory), nullable=True)
    # 서비스 유형 (법률 / 보안)
    service_type: Mapped[str] = mapped_column(String(20), default="legal", nullable=False)
    # 보안 분야 분류
    security_category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[ConfidenceLevel | None] = mapped_column(
        Enum(ConfidenceLevel), nullable=True
    )
    # 근거 법령 정보 (JSON 배열)
    legal_references: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 보안 참조 정보 (JSON 배열)
    security_references: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 답변 후처리 결과 (인용 검증 결과, 후속 질문) — {"verified_citations": [...], "followups": [...]}
    answer_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 에스컬레이션 여부
    is_escalated: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
