"""보안 RAG 파이프라인 — 벡터 검색 → 컨텍스트 조합 → LLM 답변 생성

제네릭 RAG 파이프라인(core.rag_pipeline)을 보안 도메인에 맞게 구성한 래퍼.
"""

from typing import AsyncGenerator

from core.llm import SYSTEM_PROMPT_SECURITY_QA
from core.rag_pipeline import (
    CollectionConfig,
    RAGConfig,
    rag_query as _generic_rag_query,
    rag_query_stream as _generic_rag_query_stream,
)
from core.security_classifier import analyze_security_query


# ---------------------------------------------------------------------------
# 보안 도메인 컨텍스트 빌더 / 참조 추출기
# ---------------------------------------------------------------------------

def _build_security_context(search_results: dict) -> str:
    """보안 검색 결과를 LLM 컨텍스트 문자열로 변환"""
    if not search_results or not search_results.get("documents"):
        return "관련 보안 자료를 찾을 수 없습니다."

    context_parts = []
    documents = search_results["documents"][0]
    metadatas = (
        search_results["metadatas"][0]
        if search_results.get("metadatas")
        else [{}] * len(documents)
    )

    for i, (doc, meta) in enumerate(zip(documents, metadatas)):
        guide_name = meta.get("guide_name", "")
        standard = meta.get("standard", "")
        section = meta.get("section", "")
        source = meta.get("source", "알 수 없음")

        ref_header = f"[참고자료 {i + 1}]"
        if guide_name:
            ref_header += f" {guide_name}"
        if standard:
            ref_header += f" ({standard})"
        if section:
            ref_header += f" — {section}"
        if not guide_name and not standard:
            ref_header += f" 출처: {source}"

        context_parts.append(f"{ref_header}\n{doc}\n")

    return "\n---\n".join(context_parts)


def _extract_security_references(search_results: dict) -> list[dict]:
    """보안 검색 결과에서 참조 정보 추출"""
    if not search_results or not search_results.get("metadatas"):
        return []

    references = []
    for meta in search_results["metadatas"][0]:
        ref = {
            "source": meta.get("source", ""),
            "guide_name": meta.get("guide_name", ""),
            "standard": meta.get("standard", ""),
            "section": meta.get("section", ""),
        }
        if any(ref.values()):
            references.append(ref)
    return references


# ---------------------------------------------------------------------------
# 보안 RAG 설정
# ---------------------------------------------------------------------------

_GUIDES_COLLECTION = CollectionConfig(
    name="security_guides", n_results=5, label="관련 보안 가이드", ref_key="security_references",
)
_INCIDENTS_COLLECTION = CollectionConfig(
    name="security_incidents", n_results=3, label="관련 보안 사례", ref_key="incident_references",
)

_config = RAGConfig(
    system_prompt=SYSTEM_PROMPT_SECURITY_QA,
    collections=[_GUIDES_COLLECTION, _INCIDENTS_COLLECTION],
    analyze_fn=analyze_security_query,
    build_context_fns={
        "security_guides": _build_security_context,
        "security_incidents": _build_security_context,
    },
    extract_refs_fns={
        "security_guides": _extract_security_references,
        "security_incidents": _extract_security_references,
    },
    domain_name="보안",
    enable_query_rewrite=True,
    enable_multihop=False,
    enable_citation_verification=True,  # 보안 답변도 개인정보보호법 등 법령을 인용함
    enable_followups=True,
)


# ---------------------------------------------------------------------------
# 공개 API — 기존 시그니처 유지
# ---------------------------------------------------------------------------

async def security_rag_query(
    query: str,
    session_messages: list[dict] | None = None,
) -> dict:
    """RAG 기반 보안 Q&A — 일반 응답"""
    return await _generic_rag_query(query, _config, session_messages)


async def security_rag_query_stream(
    query: str,
    session_messages: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """RAG 기반 보안 Q&A — 스트리밍 응답"""
    async for chunk in _generic_rag_query_stream(query, _config, session_messages):
        yield chunk
