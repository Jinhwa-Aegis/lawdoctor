"""멀티홉 추론 — 복합 질의 분해 및 병렬 검색

복합 법률 질의를 하위 질문으로 분해하여 각각 검색 후 결과를 통합한다.
규칙 기반 사전 필터로 단순 질의를 빠르게 걸러내고,
후보 질의에 대해서만 gpt-4o-mini를 호출하여 비용을 최소화한다.
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
class SubQuery:
    query: str
    purpose: str


@dataclass
class MultihopPlan:
    needs_multihop: bool
    sub_queries: list[SubQuery] = field(default_factory=list)
    reasoning: str = ""


# ---------------------------------------------------------------------------
# 규칙 기반 사전 필터: 멀티홉 후보 판별
# ---------------------------------------------------------------------------

_CONJUNCTION_PATTERNS = re.compile(
    r"그리고|또한|동시에|반면|아울러|한편|더불어"
)

_COMPOUND_PATTERNS = re.compile(
    r"하면서\s*.+하는\s*경우|인\s*동시에|이면서\s*동시에"
)

_COMPARISON_PATTERNS = re.compile(
    r"와\s*.+의\s*차이|과\s*.+의\s*차이|어떤\s*것이\s*우선"
    r"|비교|구분|구별|다른\s*점|같은\s*점"
)

# 법률 분야 키워드 그룹 — 2개 이상 동시 출현 시 멀티홉 후보
_DOMAIN_KEYWORDS = [
    {"개인정보", "정보보호", "정보통신망", "GDPR"},
    {"계약", "민법", "상법", "도급", "위탁", "NDA", "라이선스"},
    {"공동주택", "주택법", "관리비", "입주자"},
    {"소송", "분쟁", "민사", "형사", "가처분"},
]

_MULTIHOP_LENGTH_THRESHOLD = 80


def _is_multihop_candidate(query: str) -> bool:
    """LLM 호출 없이 멀티홉 후보 여부를 판단한다."""
    has_pattern = bool(
        _CONJUNCTION_PATTERNS.search(query)
        or _COMPOUND_PATTERNS.search(query)
        or _COMPARISON_PATTERNS.search(query)
    )

    # 다분야 키워드 동시 출현
    matched_domains = sum(
        1 for group in _DOMAIN_KEYWORDS
        if any(kw in query for kw in group)
    )
    has_multi_domain = matched_domains >= 2

    # 패턴 + 길이 조건
    if has_pattern and len(query) >= _MULTIHOP_LENGTH_THRESHOLD:
        return True
    if has_multi_domain:
        return True
    if has_pattern and has_multi_domain:
        return True

    return False


# ---------------------------------------------------------------------------
# LLM 호출: 질의 분해
# ---------------------------------------------------------------------------

_DECOMPOSE_SYSTEM = (
    "당신은 복합 법률 질의를 독립 검색 가능한 하위 질문 2~4개로 분해하는 전문가입니다. "
    "단순 질의라면 분해하지 마세요. "
    "반드시 아래 JSON 형식만 출력하세요:\n"
    '{{"needs_multihop": true/false, "sub_queries": '
    '[{{"query": "하위 질문", "purpose": "이 질문의 목적"}}], '
    '"reasoning": "분해 이유"}}'
)

_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def _decompose_query(query: str) -> MultihopPlan:
    """gpt-4o-mini를 호출하여 질의를 하위 질문으로 분해한다."""
    model = getattr(settings, "query_rewrite_model", "gpt-4o-mini")

    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=model,
            max_tokens=300,
            temperature=0,
            messages=[
                {"role": "system", "content": _DECOMPOSE_SYSTEM},
                {"role": "user", "content": f"질의: {query}\n\nJSON:"},
            ],
        )

        raw = response.choices[0].message.content or ""
        raw = raw.strip().strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

        data = json.loads(raw)

        needs = data.get("needs_multihop", False)
        reasoning = data.get("reasoning", "")

        sub_queries = []
        for sq in data.get("sub_queries", []):
            sub_queries.append(SubQuery(
                query=sq.get("query", ""),
                purpose=sq.get("purpose", ""),
            ))

        # LLM이 불필요하다고 판단하거나 하위 질의가 1개 이하이면 단일 경로
        if not needs or len(sub_queries) <= 1:
            return MultihopPlan(needs_multihop=False, reasoning=reasoning)

        logger.info(
            "multihop_plan_created",
            original=query,
            sub_query_count=len(sub_queries),
            reasoning=reasoning,
        )

        return MultihopPlan(
            needs_multihop=True,
            sub_queries=sub_queries,
            reasoning=reasoning,
        )

    except Exception as exc:
        logger.warning(
            "multihop_decompose_failed_fallback",
            error=str(exc),
            original=query,
        )
        return MultihopPlan(needs_multihop=False, reasoning=f"분해 실패: {exc}")


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

async def plan_multihop(query: str, classification=None) -> MultihopPlan:
    """질의의 멀티홉 필요 여부를 판단하고 하위 질의를 생성한다.

    규칙 기반 필터로 단순 질의를 빠르게 걸러내고,
    후보 질의에 대해서만 LLM을 호출한다.
    """
    if not _is_multihop_candidate(query):
        return MultihopPlan(needs_multihop=False)

    return await _decompose_query(query)
