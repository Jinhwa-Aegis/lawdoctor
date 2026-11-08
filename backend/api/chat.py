"""Q&A 챗봇 API 엔드포인트"""

import json
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from middleware.auth import get_current_user
from models.user import User, UserRole
from models.chat import (
    ChatSession,
    ChatMessage,
    MessageRole,
    LegalCategory,
    ConfidenceLevel,
)
from core.rag import rag_query, rag_query_stream
from core.classifier import analyze_query
from core.llm import generate_chat_title
from core.question_refiner import refine_question
from core.rag_pipeline import apply_category_override
from api.session_helpers import load_session_messages, get_or_create_session, update_session_title

logger = structlog.get_logger()

router = APIRouter()


# === Request / Response 스키마 ===

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None
    # 사용자가 직접 고른 분야 (privacy / contract / housing / litigation). 없으면 자동 분류
    category: Optional[str] = None


class RefineRequest(BaseModel):
    message: str


class RefineResponse(BaseModel):
    refined: str


def _resolve_classification(req: ChatRequest, user: User):
    """자동 분류 + 사용자 선택 분야 반영 후 소송 분야 접근 권한을 확인한다."""
    override = None
    if req.category:
        try:
            override = LegalCategory(req.category)
        except ValueError:
            raise HTTPException(status_code=400, detail="지원하지 않는 법률 분야입니다.")
    classification = apply_category_override(analyze_query(req.message), override)
    if classification.category == LegalCategory.LITIGATION and user.role != UserRole.EXECUTIVE:
        raise HTTPException(
            status_code=403,
            detail="소송·분쟁 분야는 경영진만 이용 가능합니다.",
        )
    return classification, override


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    confidence: str
    category: str
    is_escalated: bool
    legal_references: list[dict]
    consultation_references: list[dict]
    escalation_message: Optional[str] = None
    message_id: Optional[int] = None
    verified_citations: list[dict] = []
    followups: list[str] = []


class SessionListItem(BaseModel):
    id: int
    title: str
    category: Optional[str]
    created_at: str
    updated_at: str


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    confidence: Optional[str] = None
    legal_references: Optional[list[dict]] = None
    is_escalated: bool = False
    answer_meta: Optional[dict] = None
    created_at: str


# === 에스컬레이션 안내 메시지 ===

ESCALATION_MESSAGE = (
    "⚠️ 본 질의에 고위험 법률 사안이 포함되어 있습니다. "
    "AI 답변은 참고용이며, 반드시 외부 전문가 자문을 받으시기 바랍니다."
)

NO_INFO_MESSAGE = (
    "해당 질의에 대한 충분한 정보가 없습니다. "
    "외부 전문가 자문을 권장합니다."
)


# === 엔드포인트 ===

@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """법률 Q&A 질의 (일반 응답)"""
    # 질의 분석 (사용자 선택 분야 반영) — 소송 분야 접근 제한
    classification, category_override = _resolve_classification(req, user)

    # 세션 생성 또는 조회
    session, is_new = await get_or_create_session(
        db, user.id, req.session_id,
        title="새 법률 상담", category=classification.category,
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
    result = await rag_query(req.message, session_messages=prev_messages, category=category_override)

    # 새 세션이면 첫 질문으로 제목 생성
    if is_new:
        title = await generate_chat_title(req.message)
        await update_session_title(db, session.id, title)
        logger.info("세션 제목 생성", session_id=session.id, title=title)

    # 에스컬레이션 처리
    is_escalated = classification.requires_escalation
    escalation_msg = ESCALATION_MESSAGE if is_escalated else None
    if result["confidence"] == ConfidenceLevel.LOW and not is_escalated:
        escalation_msg = NO_INFO_MESSAGE
        is_escalated = True

    # AI 답변 저장
    ai_msg = ChatMessage(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content=result["answer"],
        confidence=result["confidence"],
        legal_references=result["legal_references"],
        is_escalated=is_escalated,
        answer_meta=result.get("answer_meta"),
    )
    db.add(ai_msg)
    await db.flush()

    logger.info(
        "챗봇 응답 완료",
        user_id=user.id,
        session_id=session.id,
        category=classification.category.value,
        confidence=result["confidence"].value,
        is_escalated=is_escalated,
    )

    return ChatResponse(
        session_id=session.id,
        answer=result["answer"],
        confidence=result["confidence"].value,
        category=classification.category.value,
        is_escalated=is_escalated,
        legal_references=result["legal_references"],
        consultation_references=result["consultation_references"],
        escalation_message=escalation_msg,
        message_id=ai_msg.id,
        verified_citations=(result.get("answer_meta") or {}).get("verified_citations", []),
        followups=(result.get("answer_meta") or {}).get("followups", []),
    )


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """법률 Q&A 질의 (SSE 스트리밍 응답)"""
    # 질의 분석 (사용자 선택 분야 반영) — 소송 분야 접근 제한
    classification, category_override = _resolve_classification(req, user)

    # 세션 생성 또는 조회
    session, is_new = await get_or_create_session(
        db, user.id, req.session_id,
        title="새 법률 상담", category=classification.category,
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
        answer_meta = None

        async for chunk in rag_query_stream(
            req.message, session_messages=prev_messages, category=category_override,
        ):
            if chunk["type"] == "metadata":
                metadata = chunk
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif chunk["type"] == "text":
                full_answer += chunk["content"]
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif chunk["type"] in ("status", "perspectives"):
                # 진행 상태 안내 (예: 인용 검증 중)
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif chunk["type"] == "answer_meta":
                # 인용 검증 결과 + 후속 질문
                answer_meta = {k: v for k, v in chunk.items() if k != "type"}
                # 인라인 [N] 인용 번호와 근거 자료 연결을 다시 열었을 때도 유지
                answer_meta["citations"] = metadata.get("citations", [])
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            elif chunk["type"] == "done":
                # AI 답변 DB 저장
                # 후처리에서 계산한 최종 신뢰도 우선 (검색·AI 평가·인용 검증 통합)
                confidence_val = (answer_meta or {}).get("confidence") or metadata.get("confidence", "medium")
                ai_msg = ChatMessage(
                    session_id=session.id,
                    role=MessageRole.ASSISTANT,
                    content=full_answer,
                    confidence=ConfidenceLevel(confidence_val),
                    legal_references=metadata.get("legal_references", []),
                    is_escalated=classification.requires_escalation,
                    answer_meta=answer_meta,
                )
                db.add(ai_msg)
                await db.flush()

                # 새 세션이면 첫 질문으로 제목 생성
                if is_new:
                    title = await generate_chat_title(req.message)
                    await update_session_title(db, session.id, title)
                    logger.info("세션 제목 생성", session_id=session.id, title=title)

                await db.commit()

                yield f"data: {json.dumps({'type': 'done', 'session_id': session.id, 'message_id': ai_msg.id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/refine", response_model=RefineResponse)
async def refine(req: RefineRequest, user: User = Depends(get_current_user)):
    """질문 다듬기 — 입력창 '다듬기' 버튼"""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="다듬을 질문을 입력해주세요.")
    return RefineResponse(refined=await refine_question(req.message))


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
):
    """대화 세션 목록 조회"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .where(or_(ChatSession.service_type == "legal", ChatSession.service_type.is_(None)))
        .order_by(desc(ChatSession.updated_at))
        .limit(limit)
        .offset(offset)
    )
    sessions = result.scalars().all()

    return [
        SessionListItem(
            id=s.id,
            title=s.title,
            category=s.category.value if s.category else None,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대화 세션 삭제 (메시지 포함 CASCADE 삭제)"""
    session = await db.get(ChatSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    await db.delete(session)
    await db.commit()

    logger.info("세션 삭제 완료", user_id=user.id, session_id=session_id)
    return {"detail": "세션이 삭제되었습니다."}


@router.get("/sessions/{session_id}/messages", response_model=list[MessageItem])
async def get_session_messages(
    session_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """세션의 메시지 이력 조회"""
    # 세션 소유자 확인
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
            legal_references=m.legal_references,
            is_escalated=m.is_escalated,
            answer_meta=m.answer_meta,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


