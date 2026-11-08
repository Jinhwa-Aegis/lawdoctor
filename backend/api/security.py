"""정보보안 Q&A API 엔드포인트"""

import json
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from middleware.auth import get_current_user
from models.user import User
from models.chat import (
    ChatSession,
    ChatMessage,
    MessageRole,
    ConfidenceLevel,
)
from core.security_rag import security_rag_query, security_rag_query_stream
from core.security_classifier import analyze_security_query
from core.llm import generate_chat_title
from api.session_helpers import load_session_messages, get_or_create_session, update_session_title

logger = structlog.get_logger()

router = APIRouter()


# === Request / Response 스키마 ===

class SecurityChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None


class SecurityChatResponse(BaseModel):
    session_id: int
    answer: str
    confidence: str
    category: str
    is_escalated: bool
    security_references: list[dict]
    incident_references: list[dict]
    escalation_message: Optional[str] = None


class SessionListItem(BaseModel):
    id: int
    title: str
    security_category: Optional[str]
    created_at: str
    updated_at: str


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    confidence: Optional[str] = None
    security_references: Optional[list[dict]] = None
    is_escalated: bool = False
    created_at: str


# === 에스컬레이션 안내 메시지 ===

SECURITY_ESCALATION_MESSAGE = (
    "⚠️ 본 질의에 보안 사고 관련 고위험 사안이 포함되어 있습니다. "
    "AI 답변은 참고용이며, 반드시 정보보안 담당자 또는 외부 보안 전문가와 상담하시기 바랍니다."
)

SECURITY_NO_INFO_MESSAGE = (
    "해당 질의에 대한 충분한 보안 자료가 없습니다. "
    "정보보안 담당자에게 문의하시기 바랍니다."
)


# === 엔드포인트 ===

@router.post("", response_model=SecurityChatResponse)
async def security_chat(
    req: SecurityChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보안 Q&A 질의 (일반 응답)"""
    classification = analyze_security_query(req.message)

    # 세션 생성 또는 조회
    session, is_new = await get_or_create_session(
        db, user.id, req.session_id,
        title="새 보안 상담", service_type="security",
        security_category=classification.category.value,
    )

    # 이전 대화 이력 로드
    prev_messages = await load_session_messages(db, session.id)

    # 사용자 메시지 저장
    user_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=req.message,
    )
    db.add(user_msg)
    await db.flush()

    # RAG 답변 생성
    result = await security_rag_query(req.message, session_messages=prev_messages)

    # 새 세션이면 첫 질문으로 제목 생성
    if is_new:
        title = await generate_chat_title(req.message)
        await update_session_title(db, session.id, title)
        logger.info("보안 세션 제목 생성", session_id=session.id, title=title)

    # 에스컬레이션 처리
    is_escalated = classification.requires_escalation
    escalation_msg = SECURITY_ESCALATION_MESSAGE if is_escalated else None
    if result["confidence"] == ConfidenceLevel.LOW and not is_escalated:
        escalation_msg = SECURITY_NO_INFO_MESSAGE
        is_escalated = True

    # AI 답변 저장
    ai_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=result["answer"],
        confidence=result["confidence"],
        security_references=result["security_references"],
        is_escalated=is_escalated,
    )
    db.add(ai_msg)
    await db.flush()

    logger.info(
        "보안 챗봇 응답 완료",
        user_id=user.id,
        session_id=session.id,
        category=classification.category.value,
        confidence=result["confidence"].value,
        is_escalated=is_escalated,
    )

    return SecurityChatResponse(
        session_id=session.id,
        answer=result["answer"],
        confidence=result["confidence"].value,
        category=classification.category.value,
        is_escalated=is_escalated,
        security_references=result["security_references"],
        incident_references=result["incident_references"],
        escalation_message=escalation_msg,
    )


@router.post("/stream")
async def security_chat_stream(
    req: SecurityChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보안 Q&A 질의 (SSE 스트리밍 응답)"""
    classification = analyze_security_query(req.message)

    # 세션 생성 또는 조회
    session, is_new = await get_or_create_session(
        db, user.id, req.session_id,
        title="새 보안 상담", service_type="security",
        security_category=classification.category.value,
    )

    # 이전 대화 이력 로드
    prev_messages = await load_session_messages(db, session.id)

    # 사용자 메시지 저장
    user_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.USER,
        content=req.message,
    )
    db.add(user_msg)
    await db.flush()

    async def event_generator():
        full_answer = ""
        metadata = {}

        async for chunk in security_rag_query_stream(req.message, session_messages=prev_messages):
            if chunk["type"] == "metadata":
                metadata = chunk
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif chunk["type"] == "text":
                full_answer += chunk["content"]
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif chunk["type"] == "done":
                # AI 답변 DB 저장
                confidence_val = metadata.get("confidence", "medium")
                ai_msg = ChatMessage(
                    session_id=session.id,
                    role=MessageRole.ASSISTANT,
                    content=full_answer,
                    confidence=ConfidenceLevel(confidence_val),
                    security_references=metadata.get("security_references", []),
                    is_escalated=classification.requires_escalation,
                )
                db.add(ai_msg)
                await db.flush()

                # 새 세션이면 첫 질문으로 제목 생성
                if is_new:
                    title = await generate_chat_title(req.message)
                    await update_session_title(db, session.id, title)
                    logger.info("보안 세션 제목 생성", session_id=session.id, title=title)

                await db.commit()

                yield f"data: {json.dumps({'type': 'done', 'session_id': session.id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_security_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    """보안 대화 세션 목록 조회"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .where(ChatSession.service_type == "security")
        .order_by(desc(ChatSession.updated_at))
        .limit(limit)
        .offset(offset)
    )
    sessions = result.scalars().all()

    return [
        SessionListItem(
            id=s.id,
            title=s.title,
            security_category=s.security_category,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def delete_security_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보안 대화 세션 삭제 (메시지 포함 CASCADE 삭제)"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    await db.delete(session)
    await db.commit()

    logger.info("보안 세션 삭제 완료", user_id=user.id, session_id=session_id)
    return {"detail": "세션이 삭제되었습니다."}


@router.get("/sessions/{session_id}/messages", response_model=list[MessageItem])
async def get_security_session_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보안 세션의 메시지 이력 조회"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()

    return [
        MessageItem(
            id=m.id,
            role=m.role.value,
            content=m.content,
            confidence=m.confidence.value if m.confidence else None,
            security_references=m.security_references,
            is_escalated=m.is_escalated,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


