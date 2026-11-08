"""질의 재작성 — 대명사 해소 및 핵심어 추출

벡터 검색 품질을 높이기 위해 사용자 질의를 최적화한다.
규칙 기반 필터로 재작성 필요성을 판단하고,
필요할 때만 gpt-4o-mini를 호출하여 비용을 최소화한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import structlog
from openai import AsyncOpenAI

from config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# 결과 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass
class RewrittenQuery:
    original: str                           # 원본 질의
    rewritten: str                          # 재작성된 검색 질의
    search_keywords: list[str] = field(default_factory=list)  # BM25 부스팅용 키워드
    was_rewritten: bool = False             # 재작성 수행 여부


# ---------------------------------------------------------------------------
# 규칙 기반 필터: 재작성 필요 여부 판단
# ---------------------------------------------------------------------------

_PRONOUN_PATTERNS = re.compile(
    r"그것|이것|저것|위\s*내용|앞서\s*말한|아까|방금|그\s*법|해당\s*법"
    r"|그\s*조항|이\s*조항|그\s*건|이\s*건|그거"
)

_VERBOSE_THRESHOLD = 100  # 100자 이상 서술형


def _needs_rewrite(query: str, session_messages: list[dict] | None) -> bool:
    """LLM 호출 없이 재작성 필요 여부를 판단한다."""
    # 대명사 + 이전 대화 맥락이 있을 때
    if session_messages and _PRONOUN_PATTERNS.search(query):
        return True
    # 길고 서술적인 질의
    if len(query) >= _VERBOSE_THRESHOLD:
        return True
    return False


# ---------------------------------------------------------------------------
# LLM 호출
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM = (
    "당신은 법률 검색 쿼리 최적화 전문가입니다. "
    "사용자의 입력을 벡터 검색에 최적화된 간결한 형태로 변환하세요. "
    "반드시 아래 JSON 형식만 출력하세요:\n"
    '{{"rewritten": "재작성된 검색 질의", "keywords": ["키워드1", "키워드2"]}}'
)

# OpenAI 클라이언트 (지연 초기화)
_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def _call_rewrite_llm(
    query: str, session_messages: list[dict] | None
) -> RewrittenQuery:
    """gpt-4o-mini를 호출하여 질의를 재작성한다."""
    # 최근 2턴 대화 맥락 구성
    context = ""
    if session_messages:
        recent = session_messages[-4:]  # 최근 2턴 (user+assistant × 2)
        turns = []
        for msg in recent:
            role = "사용자" if msg["role"] == "user" else "AI"
            content = msg.get("content", "")
            if len(content) > 200:
                content = content[:200] + "..."
            turns.append(f"{role}: {content}")
        context = f"이전 대화:\n" + "\n".join(turns) + "\n\n"

    user_content = f"{context}원본 질의: {query}\n\nJSON:"

    model = getattr(settings, "query_rewrite_model", "gpt-4o-mini")

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=model,
            max_tokens=150,
            temperature=0,
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": user_content},
            ],
        )

        raw = response.choices[0].message.content or ""
        # JSON 파싱 (코드 블록 제거)
        raw = raw.strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

        data = json.loads(raw)
        rewritten = data.get("rewritten", query)
        keywords = data.get("keywords", [])

        logger.info(
            "query_rewritten",
            original=query,
            rewritten=rewritten,
            keywords=keywords,
        )

        return RewrittenQuery(
            original=query,
            rewritten=rewritten,
            search_keywords=keywords,
            was_rewritten=True,
        )

    except Exception as exc:
        logger.warning(
            "query_rewrite_failed_fallback",
            error=str(exc),
            original=query,
        )
        # 폴백: 원본 그대로
        return RewrittenQuery(original=query, rewritten=query)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

async def rewrite_query(
    query: str,
    session_messages: list[dict] | None = None,
) -> RewrittenQuery:
    """질의를 분석하여 필요 시 재작성한다.

    규칙 기반 필터로 재작성 필요성을 먼저 판단하고,
    필요할 때만 LLM을 호출하여 비용을 최소화한다.
    실패 시 원본 질의를 그대로 반환하여 검색 중단을 방지한다.
    """
    if not _needs_rewrite(query, session_messages):
        return RewrittenQuery(original=query, rewritten=query)

    return await _call_rewrite_llm(query, session_messages)
