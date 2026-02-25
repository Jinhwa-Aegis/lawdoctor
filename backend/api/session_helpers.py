"""채팅 세션 공통 헬퍼 함수"""

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.chat import ChatSession, ChatMessage


async def load_session_messages(
    db: AsyncSession,
    session_id: int,
    limit: int = 10,
) -> list[dict]:
    """세션의 최근 메시지를 LLM 형식으로 로드"""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))

    return [
        {"role": m.role.value, "content": m.content}
        for m in messages
    ]


async def get_or_create_session(
    db: AsyncSession,
    user_id: int,
    session_id: int | None,
    *,
    title: str = "새 상담",
    service_type: str | None = None,
    category=None,
    security_category: str | None = None,
) -> tuple[ChatSession, bool]:
    """세션 조회 또는 새로 생성. (session, is_new) 튜플 반환."""
    if session_id:
        session = await db.get(ChatSession, session_id)
        if session and session.user_id == user_id:
            return session, False

    kwargs = dict(user_id=user_id, title=title)
    if service_type:
        kwargs["service_type"] = service_type
    if category is not None:
        kwargs["category"] = category
    if security_category is not None:
        kwargs["security_category"] = security_category

    session = ChatSession(**kwargs)
    db.add(session)
    await db.flush()
    return session, True


async def update_session_title(
    db: AsyncSession,
    session_id: int,
    title: str,
) -> None:
    """세션 제목 업데이트"""
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(title=title)
    )
