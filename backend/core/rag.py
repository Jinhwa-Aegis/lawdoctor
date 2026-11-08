"""법률 RAG 파이프라인 — 벡터 검색 → 컨텍스트 조합 → LLM 답변 생성

제네릭 RAG 파이프라인(core.rag_pipeline)을 법률 도메인에 맞게 구성한 래퍼.
"""

from typing import AsyncGenerator

from core.classifier import analyze_query
from core.llm import SYSTEM_PROMPT_LEGAL_QA
from core.rag_pipeline import (
    CollectionConfig,
    RAGConfig,
    rag_query as _generic_rag_query,
    rag_query_stream as _generic_rag_query_stream,
)
from models.chat import LegalCategory


# ---------------------------------------------------------------------------
# 카테고리별 법령명 매핑 (메타데이터 필터링)
# ---------------------------------------------------------------------------

_CATEGORY_LAW_NAMES: dict[LegalCategory, list[str]] = {
    LegalCategory.PRIVACY: [
        "개인정보 보호법",
        "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    ],
    LegalCategory.CONTRACT: ["민법", "상법"],
    LegalCategory.HOUSING: ["공동주택관리법", "주택법"],
    LegalCategory.LITIGATION: [],  # 필터 없이 전체 검색
}


def _build_laws_where_filter(classification) -> dict | None:
    """분류 결과에 따라 법령 컬렉션의 where 필터를 생성한다."""
    law_names = _CATEGORY_LAW_NAMES.get(classification.category, [])
    if not law_names:
        return None
    if len(law_names) == 1:
        return {"source": {"$eq": law_names[0]}}
    return {"$or": [{"source": {"$eq": name}} for name in law_names]}


# ---------------------------------------------------------------------------
# 법률 도메인 컨텍스트 빌더 / 참조 추출기
# ---------------------------------------------------------------------------

def _build_legal_context(search_results: dict) -> str:
    """법률 검색 결과를 LLM 컨텍스트 문자열로 변환"""
    if not search_results or not search_results.get("documents"):
        return "관련 법령 및 자문 이력을 찾을 수 없습니다."

    context_parts = []
    documents = search_results["documents"][0]
    metadatas = (
        search_results["metadatas"][0]
        if search_results.get("metadatas")
        else [{}] * len(documents)
    )
    distances = (
        search_results["distances"][0]
        if search_results.get("distances")
        else [0.0] * len(documents)
    )

    for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
        source = meta.get("source", "알 수 없음")
        source_type = meta.get("source_type", "")
        law_name = meta.get("law_name", "")
        case_name = meta.get("case_name", "")

        header = f"[참고자료 {i + 1}]"
        if source_type == "precedent" and case_name:
            court = meta.get("court", "")
            case_number = meta.get("case_number", "")
            header += f" 판례: {case_name}"
            if court:
                header += f" ({court}"
                if case_number:
                    header += f" {case_number}"
                header += ")"
        elif law_name:
            header += f" 법령: {law_name}"
        elif source_type == "consultation":
            header += f" 자문 이력: {source}"
        else:
            header += f" 출처: {source}"

        context_parts.append(f"{header}\n{doc}\n")

    return "\n---\n".join(context_parts)


def _extract_legal_references(search_results: dict) -> list[dict]:
    """법률 검색 결과에서 참고 문헌 정보 추출

    각 참조에 조문 번호, 조문 제목, 조문 발췌(excerpt)를 포함하여
    사용자가 근거 법령을 상세하게 확인할 수 있도록 한다.
    """
    if not search_results or not search_results.get("metadatas"):
        return []

    metadatas = search_results["metadatas"][0]
    documents = (
        search_results["documents"][0]
        if search_results.get("documents")
        else [""] * len(metadatas)
    )

    # 중복 제거용 (법령+조문번호 또는 판례번호 기준)
    seen: set[str] = set()
    references = []

    for meta, doc_text in zip(metadatas, documents):
        source_type = meta.get("source_type", "")

        # 조문 발췌: 컨텍스트 프리픽스(【...】) 제거 후 앞부분 발췌
        excerpt = doc_text or ""
        if excerpt.startswith("【"):
            newline_pos = excerpt.find("\n")
            if newline_pos > 0:
                excerpt = excerpt[newline_pos + 1:]
        excerpt = excerpt.strip()
        if len(excerpt) > 200:
            excerpt = excerpt[:200] + "…"

        if source_type == "precedent":
            dedup_key = f"prec:{meta.get('case_number', '')}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            ref = {
                "source": meta.get("source", ""),
                "source_type": source_type,
                "case_name": meta.get("case_name", ""),
                "case_number": meta.get("case_number", ""),
                "court": meta.get("court", ""),
                "decision_date": meta.get("decision_date", ""),
                "excerpt": excerpt,
            }
        elif source_type == "law":
            article_number = meta.get("article_number", "")
            article_title = meta.get("article_title", "")
            law_name = meta.get("law_name", meta.get("source", ""))

            dedup_key = f"law:{law_name}:제{article_number}조"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            ref = {
                "source": meta.get("source", ""),
                "source_type": source_type,
                "law_name": law_name,
                "article_number": article_number,
                "article_title": article_title,
                "excerpt": excerpt,
            }
        else:
            # consultation 등
            dedup_key = f"other:{meta.get('source', '')}:{meta.get('chunk_index', '')}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            ref = {
                "source": meta.get("source", ""),
                "source_type": source_type,
                "excerpt": excerpt,
            }

        if any(v for k, v in ref.items() if k != "source_type"):
            references.append(ref)

    return references


# ---------------------------------------------------------------------------
# 법률 RAG 설정
# ---------------------------------------------------------------------------

_LAWS_COLLECTION = CollectionConfig(
    name="laws",
    n_results=5,
    label="관련 법령",
    ref_key="legal_references",
    build_where_fn=_build_laws_where_filter,
    enable_hybrid=True,
)
_CONSULTATIONS_COLLECTION = CollectionConfig(
    name="consultations",
    n_results=3,
    label="관련 자문 이력",
    ref_key="consultation_references",
    enable_hybrid=True,
)
_PRECEDENTS_COLLECTION = CollectionConfig(
    name="precedents",
    n_results=3,
    label="관련 판례",
    ref_key="precedent_references",
    enable_hybrid=True,
)

_config = RAGConfig(
    system_prompt=SYSTEM_PROMPT_LEGAL_QA,
    collections=[_LAWS_COLLECTION, _CONSULTATIONS_COLLECTION, _PRECEDENTS_COLLECTION],
    analyze_fn=analyze_query,
    build_context_fns={
        "laws": _build_legal_context,
        "consultations": _build_legal_context,
        "precedents": _build_legal_context,
    },
    extract_refs_fns={
        "laws": _extract_legal_references,
        "consultations": _extract_legal_references,
        "precedents": _extract_legal_references,
    },
    domain_name="법률",
    enable_query_rewrite=True,
    enable_multihop=True,
)


# ---------------------------------------------------------------------------
# 공개 API — 기존 시그니처 유지
# ---------------------------------------------------------------------------

async def rag_query(
    query: str,
    session_messages: list[dict] | None = None,
) -> dict:
    """RAG 기반 법률 Q&A — 일반 응답"""
    return await _generic_rag_query(query, _config, session_messages)


async def rag_query_stream(
    query: str,
    session_messages: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """RAG 기반 법률 Q&A — 스트리밍 응답"""
    async for chunk in _generic_rag_query_stream(query, _config, session_messages):
        yield chunk

