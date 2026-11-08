"""관리자 API 엔드포인트"""

import os
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import aiofiles
import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import get_db
from middleware.auth import get_current_user, require_role
from models.user import User, UserRole
from models.chat import ChatSession, ChatMessage, MessageRole
from models.feedback import Feedback, FeedbackType
from models.document import Document, DocumentType, DocumentSource
from data.vector_store import get_vector_store

logger = structlog.get_logger()

router = APIRouter()

KST = ZoneInfo("Asia/Seoul")
ACTIVITY_DAYS = 14
# 인용 검증에서 문제로 보는 상태 (core.citation_verifier 의 STATUS_* 값)
_CITATION_PROBLEM_STATUSES = {"repealed", "not_found", "unknown_law"}


def count_citation_issues(answer_meta: dict | None) -> int:
    """답변 메타에서 문제(폐지·없음·미확인 법령) 인용 수"""
    if not isinstance(answer_meta, dict):
        return 0
    citations = answer_meta.get("verified_citations") or []
    return sum(
        1 for c in citations
        if isinstance(c, dict) and c.get("status") in _CITATION_PROBLEM_STATUSES
    )


def summarize_activity(rows: list[dict], days: int, today: date) -> dict:
    """최근 days일의 일별 질문 수와 답변 품질 지표를 집계한다.

    rows: {"role", "created_at"(aware datetime), "confidence", "answer_meta"}
    날짜는 한국 시간 기준으로 나눈다.
    """
    start = today - timedelta(days=days - 1)
    per_day: Counter = Counter()
    answers = citation_issue_answers = low_confidence_answers = 0
    for r in rows:
        created = r["created_at"]
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        day = created.astimezone(KST).date()
        if day < start or day > today:
            continue
        if r["role"] == MessageRole.USER.value:
            per_day[day] += 1
        elif r["role"] == MessageRole.ASSISTANT.value:
            answers += 1
            if count_citation_issues(r["answer_meta"]) > 0:
                citation_issue_answers += 1
            if r["confidence"] == "low":
                low_confidence_answers += 1
    daily = [
        {"date": (start + timedelta(days=i)).isoformat(), "count": per_day[start + timedelta(days=i)]}
        for i in range(days)
    ]
    return {
        "daily_questions": daily,
        "recent_answers": answers,
        "citation_issue_answers": citation_issue_answers,
        "low_confidence_answers": low_confidence_answers,
    }


def _excerpt(text: str, limit: int = 240) -> str:
    """답변 앞부분 요약 (표 행과 마크다운 기호 제거)"""
    lines = [ln for ln in (text or "").splitlines() if not ln.lstrip().startswith("|")]
    flat = " ".join("\n".join(lines).replace("#", "").replace("**", "").split())
    return flat if len(flat) <= limit else flat[:limit].rstrip() + "…"


# === Request / Response 스키마 ===

class UserCreateRequest(BaseModel):
    username: str
    display_name: str
    role: UserRole = UserRole.STAFF


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: str


class UserUpdateRequest(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class DashboardStats(BaseModel):
    total_users: int
    total_sessions: int
    total_messages: int
    total_feedbacks: int
    positive_feedback_ratio: float
    # 최근 ACTIVITY_DAYS일 지표
    daily_questions: list[dict] = []
    recent_answers: int = 0
    citation_issue_answers: int = 0
    low_confidence_answers: int = 0


class RecentFeedbackItem(BaseModel):
    id: int
    message_id: int
    session_id: int
    feedback_type: str
    reason: Optional[str] = None
    comment: Optional[str] = None
    user_name: str
    question: str
    answer_excerpt: str
    confidence: Optional[str] = None
    citation_issues: int = 0
    created_at: str


class PdfUploadResponse(BaseModel):
    filename: str
    chunks: int
    collection: str
    message: str
    document_id: Optional[int] = None


class IngestRequest(BaseModel):
    guides_dir: Optional[str] = None
    incidents_dir: Optional[str] = None


class IngestResponse(BaseModel):
    builtin: dict
    guide_pdfs: dict
    incident_pdfs: dict


class LawIngestRequest(BaseModel):
    law_names: Optional[list[str]] = None


class LawIngestResponse(BaseModel):
    results: dict[str, int]
    total_chunks: int


class PrecedentIngestRequest(BaseModel):
    keywords: Optional[list[str]] = None
    max_per_keyword: int = 10


class PrecedentIngestResponse(BaseModel):
    results: dict[str, int]
    total_chunks: int


# === 엔드포인트 ===

@router.post("/users", response_model=UserResponse)
async def create_user(
    req: UserCreateRequest,
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """사용자 생성 (경영진 전용)"""
    # 중복 확인
    existing = await db.execute(
        select(User).where(User.username == req.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="이미 존재하는 사용자명입니다.")

    new_user = User(
        username=req.username,
        display_name=req.display_name,
        role=req.role,
    )
    db.add(new_user)
    await db.flush()

    logger.info("사용자 생성", admin_id=user.id, new_user=req.username)

    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        display_name=new_user.display_name,
        role=new_user.role.value,
        is_active=new_user.is_active,
        created_at=new_user.created_at.isoformat(),
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """사용자 목록 조회 (경영진 전용)"""
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()

    return [
        UserResponse(
            id=u.id,
            username=u.username,
            display_name=u.display_name,
            role=u.role.value,
            is_active=u.is_active,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """사용자 정보 수정 (경영진 전용)"""
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if req.role is not None:
        target.role = req.role
    if req.is_active is not None:
        target.is_active = req.is_active

    await db.flush()
    logger.info("사용자 수정", admin_id=user.id, target_id=user_id)

    return UserResponse(
        id=target.id,
        username=target.username,
        display_name=target.display_name,
        role=target.role.value,
        is_active=target.is_active,
        created_at=target.created_at.isoformat(),
    )


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard(
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """대시보드 통계 (경영진 전용)"""
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
    total_sessions = (await db.execute(select(func.count(ChatSession.id)))).scalar() or 0
    total_messages = (await db.execute(select(func.count(ChatMessage.id)))).scalar() or 0
    total_feedbacks = (await db.execute(select(func.count(Feedback.id)))).scalar() or 0

    positive_feedbacks = (
        await db.execute(
            select(func.count(Feedback.id)).where(
                Feedback.feedback_type == FeedbackType.POSITIVE
            )
        )
    ).scalar() or 0

    ratio = round(positive_feedbacks / total_feedbacks * 100, 1) if total_feedbacks > 0 else 0.0

    # 최근 N일 활동·답변 품질 — 사용자 수(10~30명) 규모라 Python에서 집계
    since = datetime.now(timezone.utc) - timedelta(days=ACTIVITY_DAYS)
    recent_rows = (
        await db.execute(
            select(ChatMessage.role, ChatMessage.created_at, ChatMessage.confidence, ChatMessage.answer_meta)
            .where(ChatMessage.created_at >= since)
        )
    ).all()
    activity = summarize_activity(
        [
            {
                "role": r.role.value if hasattr(r.role, "value") else r.role,
                "created_at": r.created_at,
                "confidence": r.confidence.value if r.confidence is not None else None,
                "answer_meta": r.answer_meta,
            }
            for r in recent_rows
        ],
        days=ACTIVITY_DAYS,
        today=datetime.now(KST).date(),
    )

    return DashboardStats(
        total_users=total_users,
        total_sessions=total_sessions,
        total_messages=total_messages,
        total_feedbacks=total_feedbacks,
        positive_feedback_ratio=ratio,
        **activity,
    )


@router.get("/feedback/recent", response_model=list[RecentFeedbackItem])
async def get_recent_feedback(
    feedback_type: FeedbackType = Query(default=FeedbackType.NEGATIVE),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """최근 피드백과 해당 질문·답변 (경영진 전용) — 답변 품질 점검용"""
    rows = (
        await db.execute(
            select(Feedback, ChatMessage, User.display_name)
            .join(ChatMessage, Feedback.message_id == ChatMessage.id)
            .join(User, Feedback.user_id == User.id)
            .where(Feedback.feedback_type == feedback_type)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        )
    ).all()

    items: list[RecentFeedbackItem] = []
    for fb, msg, display_name in rows:
        # 답변 직전의 사용자 질문
        question = (
            await db.execute(
                select(ChatMessage.content)
                .where(
                    ChatMessage.session_id == msg.session_id,
                    ChatMessage.id < msg.id,
                    ChatMessage.role == MessageRole.USER,
                )
                .order_by(ChatMessage.id.desc())
                .limit(1)
            )
        ).scalar()
        items.append(RecentFeedbackItem(
            id=fb.id,
            message_id=msg.id,
            session_id=msg.session_id,
            feedback_type=fb.feedback_type.value,
            reason=fb.reason.value if fb.reason else None,
            comment=fb.comment,
            user_name=display_name,
            question=question or "",
            answer_excerpt=_excerpt(msg.content),
            confidence=msg.confidence.value if msg.confidence else None,
            citation_issues=count_citation_issues(msg.answer_meta),
            created_at=fb.created_at.isoformat(),
        ))
    return items


@router.post("/ingest/security", response_model=IngestResponse)
async def ingest_security_data(
    req: IngestRequest,
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
):
    """보안 데이터 적재 (내장 지식베이스 + PDF, 경영진 전용)"""
    from data.security_ingest import ingest_all_security_data

    try:
        result = await ingest_all_security_data(
            guides_dir=req.guides_dir,
            incidents_dir=req.incidents_dir,
        )
        logger.info("보안 데이터 적재 완료", admin_id=user.id, result=result)
        return IngestResponse(**result)

    except Exception as e:
        logger.error("보안 데이터 적재 실패", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail="보안 데이터 적재 중 오류가 발생했습니다. 관리자에게 문의해주세요.")


@router.post("/ingest/laws", response_model=LawIngestResponse)
async def ingest_laws(
    req: LawIngestRequest,
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
):
    """법령 데이터 적재 — 국가법령정보센터 API (경영진 전용)"""
    from data.law_api import fetch_and_ingest_laws

    try:
        results = await fetch_and_ingest_laws(law_names=req.law_names)
        total_chunks = sum(results.values())
        logger.info("법령 적재 완료", admin_id=user.id, total_chunks=total_chunks)
        return LawIngestResponse(results=results, total_chunks=total_chunks)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("법령 적재 실패", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="법령 데이터 적재 중 오류가 발생했습니다. 관리자에게 문의해주세요.",
        )


@router.post("/ingest/precedents", response_model=PrecedentIngestResponse)
async def ingest_precedents(
    req: PrecedentIngestRequest,
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
):
    """판례 데이터 적재 — 국가법령정보센터 API (경영진 전용)"""
    from data.law_api import fetch_and_ingest_precedents

    try:
        results = await fetch_and_ingest_precedents(
            keywords=req.keywords,
            max_per_keyword=req.max_per_keyword,
        )
        total_chunks = sum(results.values())
        logger.info("판례 적재 완료", admin_id=user.id, total_chunks=total_chunks)
        return PrecedentIngestResponse(results=results, total_chunks=total_chunks)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("판례 적재 실패", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="판례 데이터 적재 중 오류가 발생했습니다. 관리자에게 문의해주세요.",
        )


@router.get("/vectors/stats")
async def get_vector_stats(
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
):
    """벡터 DB 컬렉션 통계 조회 (경영진 전용)"""
    collections = ["laws", "consultations", "precedents", "security_guides", "security_incidents"]

    try:
        vs = get_vector_store()
    except Exception as e:
        logger.warning("chromadb_connection_failed", error=str(e))
        return {name: {"name": name, "count": 0, "error": "ChromaDB 연결 실패"} for name in collections}

    stats = {}
    for name in collections:
        try:
            stats[name] = vs.get_collection_stats(name)
        except Exception:
            stats[name] = {"name": name, "count": 0, "error": "컬렉션 없음"}

    return stats


@router.get("/security/metadata")
async def get_security_metadata(
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
):
    """보안 자료 표준/섹션 메타데이터 조회 (경영진 전용)

    내장 지식베이스 + ChromaDB에 저장된 문서의 메타데이터에서
    고유한 표준(standard)과 섹션(section) 목록을 반환한다.
    """
    from data.security_ingest import (
        BUILTIN_SECURITY_GUIDES,
        BUILTIN_SECURITY_INCIDENTS,
    )

    # 표준 → 섹션 집합 매핑
    standards_map: dict[str, set[str]] = {}

    # 1. 내장 지식베이스에서 수집
    for item in BUILTIN_SECURITY_GUIDES + BUILTIN_SECURITY_INCIDENTS:
        std = item.get("standard", "")
        sec = item.get("section", "")
        if std:
            if std not in standards_map:
                standards_map[std] = set()
            if sec:
                standards_map[std].add(sec)

    # 2. ChromaDB에서 업로드된 문서의 메타데이터 수집
    vs = get_vector_store()
    for collection_name in ("security_guides", "security_incidents"):
        try:
            collection = vs.get_collection(collection_name)
            result = collection.get(include=["metadatas"])
            for meta in result.get("metadatas", []):
                std = meta.get("standard", "")
                sec = meta.get("section", "")
                if std and std != "":
                    if std not in standards_map:
                        standards_map[std] = set()
                    if sec:
                        standards_map[std].add(sec)
        except Exception:
            pass

    # set → sorted list 변환
    return {
        std: sorted(list(sections))
        for std, sections in sorted(standards_map.items())
    }


ALLOWED_DOC_EXTENSIONS = {".pdf", ".docx", ".hwp", ".hwpx"}


@router.post("/upload/legal", response_model=PdfUploadResponse)
async def upload_legal_document(
    file: UploadFile = File(...),
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """법률 문서 업로드 및 벡터 DB 적재 (경영진 전용, PDF/DOCX/HWP)"""
    from data.ingest import ingest_pdf

    # 확장자 검증
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 지원 형식: {', '.join(ALLOWED_DOC_EXTENSIONS)}",
        )

    # 파일 크기 제한
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {settings.max_upload_size_mb}MB를 초과합니다.",
        )

    # 임시 파일 저장
    os.makedirs(settings.upload_dir, exist_ok=True)
    uuid_stem = uuid.uuid4().hex
    filename = f"{uuid_stem}{ext}"
    filepath = os.path.join(settings.upload_dir, filename)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    logger.info(
        "법률 문서 업로드",
        admin_id=user.id,
        filename=file.filename,
        size=len(content),
    )

    try:
        chunk_count = await ingest_pdf(filepath, source_type="consultation")

        # Document 레코드 생성
        doc = Document(
            original_filename=file.filename or filename,
            file_extension=ext,
            file_size_bytes=len(content),
            document_type=DocumentType.LEGAL,
            source=DocumentSource.UPLOADED,
            collection_name="consultations",
            chunk_count=chunk_count,
            chunk_id_prefix=uuid_stem,
            uploaded_by=user.id,
        )
        db.add(doc)
        await db.flush()

        return PdfUploadResponse(
            filename=file.filename or filename,
            chunks=chunk_count,
            collection="consultations",
            message=f"법률 자료 적재 완료: {chunk_count}개 청크 생성",
            document_id=doc.id,
        )
    except Exception as e:
        logger.error("법률 문서 적재 실패", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="문서 적재 중 오류가 발생했습니다. 관리자에게 문의해주세요.",
        )
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@router.post("/upload/security", response_model=PdfUploadResponse)
async def upload_security_document(
    file: UploadFile = File(...),
    collection: str = Form("security_guides"),
    guide_name: str = Form(""),
    standard: str = Form(""),
    section: str = Form(""),
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """보안 문서 업로드 및 벡터 DB 적재 (경영진 전용, PDF/DOCX/HWP)"""
    from data.security_ingest import ingest_security_pdf

    # 컬렉션 검증
    if collection not in ("security_guides", "security_incidents"):
        raise HTTPException(
            status_code=400,
            detail="컬렉션은 security_guides 또는 security_incidents만 가능합니다.",
        )

    # 확장자 검증
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 지원 형식: {', '.join(ALLOWED_DOC_EXTENSIONS)}",
        )

    # 파일 크기 제한
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {settings.max_upload_size_mb}MB를 초과합니다.",
        )

    # 임시 파일 저장
    os.makedirs(settings.upload_dir, exist_ok=True)
    uuid_stem = uuid.uuid4().hex
    filename = f"{uuid_stem}{ext}"
    filepath = os.path.join(settings.upload_dir, filename)

    async with aiofiles.open(filepath, "wb") as f:
        await f.write(content)

    logger.info(
        "보안 문서 업로드",
        admin_id=user.id,
        filename=file.filename,
        collection=collection,
        size=len(content),
    )

    try:
        chunk_count = await ingest_security_pdf(
            filepath=filepath,
            guide_name=guide_name,
            standard=standard,
            section=section,
            collection=collection,
        )

        # Document 레코드 생성 (보안 문서 chunk ID prefix: sec_{uuid_stem})
        doc = Document(
            original_filename=file.filename or filename,
            file_extension=ext,
            file_size_bytes=len(content),
            document_type=DocumentType.SECURITY,
            source=DocumentSource.UPLOADED,
            collection_name=collection,
            chunk_count=chunk_count,
            chunk_id_prefix=f"sec_{uuid_stem}",
            guide_name=guide_name or None,
            standard=standard or None,
            section=section or None,
            uploaded_by=user.id,
        )
        db.add(doc)
        await db.flush()

        return PdfUploadResponse(
            filename=file.filename or filename,
            chunks=chunk_count,
            collection=collection,
            message=f"보안 자료 적재 완료: {chunk_count}개 청크 생성",
            document_id=doc.id,
        )
    except Exception as e:
        logger.error("보안 문서 적재 실패", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="문서 적재 중 오류가 발생했습니다. 관리자에게 문의해주세요.",
        )
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


# === 문서 관리 스키마 ===

class DocumentResponse(BaseModel):
    id: int
    original_filename: str
    file_extension: str
    file_size_bytes: int
    document_type: str
    source: str
    collection_name: str
    chunk_count: int
    chunk_id_prefix: str
    guide_name: Optional[str] = None
    standard: Optional[str] = None
    section: Optional[str] = None
    uploaded_by: Optional[int] = None
    created_at: str
    updated_at: str


class DocumentUpdateRequest(BaseModel):
    guide_name: Optional[str] = None
    standard: Optional[str] = None
    section: Optional[str] = None


class DocumentDeleteResponse(BaseModel):
    message: str
    chromadb_warning: Optional[str] = None


# === 문서 관리 엔드포인트 ===

@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    document_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    collection: Optional[str] = Query(None),
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """업로드 문서 목록 조회 (경영진 전용)"""
    query = select(Document).order_by(Document.created_at.desc())

    if document_type:
        query = query.where(Document.document_type == document_type)
    if collection:
        query = query.where(Document.collection_name == collection)
    if search:
        query = query.where(Document.original_filename.ilike(f"%{search}%"))

    result = await db.execute(query)
    docs = result.scalars().all()

    return [
        DocumentResponse(
            id=d.id,
            original_filename=d.original_filename,
            file_extension=d.file_extension,
            file_size_bytes=d.file_size_bytes,
            document_type=d.document_type.value,
            source=d.source.value,
            collection_name=d.collection_name,
            chunk_count=d.chunk_count,
            chunk_id_prefix=d.chunk_id_prefix,
            guide_name=d.guide_name,
            standard=d.standard,
            section=d.section,
            uploaded_by=d.uploaded_by,
            created_at=d.created_at.isoformat(),
            updated_at=d.updated_at.isoformat(),
        )
        for d in docs
    ]


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    req: DocumentUpdateRequest,
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """문서 메타데이터 수정 (경영진 전용)"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    if doc.source == DocumentSource.BUILTIN:
        raise HTTPException(status_code=403, detail="내장 지식베이스는 수정할 수 없습니다.")

    # PostgreSQL 업데이트
    if req.guide_name is not None:
        doc.guide_name = req.guide_name
    if req.standard is not None:
        doc.standard = req.standard
    if req.section is not None:
        doc.section = req.section

    await db.flush()

    # ChromaDB 메타데이터 동기화
    try:
        vs = get_vector_store()
        chunk_ids = await vs.async_get_ids_by_prefix(
            doc.collection_name, doc.chunk_id_prefix
        )
        if chunk_ids:
            updated_meta = {}
            if req.guide_name is not None:
                updated_meta["guide_name"] = req.guide_name
            if req.standard is not None:
                updated_meta["standard"] = req.standard
            if req.section is not None:
                updated_meta["section"] = req.section

            if updated_meta:
                metadatas = [updated_meta for _ in chunk_ids]
                await vs.async_update_metadatas(
                    doc.collection_name, chunk_ids, metadatas
                )
    except Exception as e:
        logger.warning(
            "chromadb_metadata_sync_failed",
            document_id=document_id,
            error=str(e),
        )

    logger.info("문서 메타데이터 수정", admin_id=user.id, document_id=document_id)

    return DocumentResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        file_extension=doc.file_extension,
        file_size_bytes=doc.file_size_bytes,
        document_type=doc.document_type.value,
        source=doc.source.value,
        collection_name=doc.collection_name,
        chunk_count=doc.chunk_count,
        chunk_id_prefix=doc.chunk_id_prefix,
        guide_name=doc.guide_name,
        standard=doc.standard,
        section=doc.section,
        uploaded_by=doc.uploaded_by,
        created_at=doc.created_at.isoformat(),
        updated_at=doc.updated_at.isoformat(),
    )


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: int,
    user: User = Depends(require_role(UserRole.EXECUTIVE)),
    db: AsyncSession = Depends(get_db),
):
    """문서 삭제 — ChromaDB 청크 + PostgreSQL 레코드 삭제 (경영진 전용)"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    if doc.source == DocumentSource.BUILTIN:
        raise HTTPException(status_code=403, detail="내장 지식베이스는 삭제할 수 없습니다.")

    # ChromaDB 청크 삭제
    chromadb_warning = None
    try:
        vs = get_vector_store()
        chunk_ids = await vs.async_get_ids_by_prefix(
            doc.collection_name, doc.chunk_id_prefix
        )
        if chunk_ids:
            await vs.async_delete_by_ids(doc.collection_name, chunk_ids)
            logger.info(
                "chromadb_chunks_deleted",
                document_id=document_id,
                collection=doc.collection_name,
                chunk_count=len(chunk_ids),
            )
    except Exception as e:
        logger.warning(
            "chromadb_delete_failed",
            document_id=document_id,
            error=str(e),
        )
        chromadb_warning = f"ChromaDB 청크 삭제 실패: {str(e)}"

    # PostgreSQL 레코드 삭제
    filename = doc.original_filename
    await db.delete(doc)
    await db.flush()

    logger.info("문서 삭제", admin_id=user.id, document_id=document_id, filename=filename)

    return DocumentDeleteResponse(
        message=f"문서 '{filename}' 삭제 완료",
        chromadb_warning=chromadb_warning,
    )
