"""업로드 문서 관리 모델"""

import enum
from datetime import datetime

from sqlalchemy import String, Integer, Enum, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class DocumentType(str, enum.Enum):
    LEGAL = "legal"
    SECURITY = "security"


class DocumentSource(str, enum.Enum):
    UPLOADED = "uploaded"   # 사용자 업로드
    BUILTIN = "builtin"    # 내장 지식베이스 (삭제 불가)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType), nullable=False
    )
    source: Mapped[DocumentSource] = mapped_column(
        Enum(DocumentSource), default=DocumentSource.UPLOADED, nullable=False
    )

    collection_name: Mapped[str] = mapped_column(String(100), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_id_prefix: Mapped[str] = mapped_column(String(200), nullable=False)

    # 보안 자료 메타데이터
    guide_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard: Mapped[str | None] = mapped_column(String(200), nullable=True)
    section: Mapped[str | None] = mapped_column(String(200), nullable=True)

    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
