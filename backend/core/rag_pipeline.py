"""제네릭 RAG 파이프라인 — 벡터 검색 → 컨텍스트 조합 → LLM 답변 생성

법률 RAG(core.rag)와 보안 RAG(core.security_rag)의 공통 로직을 통합한다.
각 도메인은 RAGConfig를 통해 컬렉션, 시스템 프롬프트, 컨텍스트 빌더,
참조 추출기 등을 주입하여 동작을 커스터마이즈한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncGenerator, Callable

import asyncio

import structlog

from core.embeddings import embed_text
from core.hybrid_search import get_bm25_index, reciprocal_rank_fusion
from core.llm import get_llm_client
from core.reranker import rerank_results
from data.vector_store import get_vector_store
from models.chat import ConfidenceLevel

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 신뢰도 임계값 상수
# ---------------------------------------------------------------------------
_HIGH_CONFIDENCE_DISTANCE = 0.3
_MEDIUM_CONFIDENCE_DISTANCE = 0.6


# ---------------------------------------------------------------------------
# 설정 데이터 클래스
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CollectionConfig:
    """벡터 검색 컬렉션 설정"""

    name: str        # ChromaDB 컬렉션 이름
    n_results: int   # 검색 결과 개수
    label: str       # 컨텍스트 헤더 라벨 (예: "관련 법령")
    ref_key: str     # 결과 딕셔너리의 참조 키 (예: "legal_references")
    build_where_fn: Callable | None = None       # 메타데이터 필터 생성 함수
    retrieval_multiplier: int = 3                # 리랭킹용 초과 검색 배수
    enable_hybrid: bool = False                  # 하이브리드 검색(BM25+벡터) 활성화


# 컨텍스트 빌더 / 참조 추출기의 타입 별칭
BuildContextFn = Callable[[dict], str]
ExtractRefsFn = Callable[[dict], list[dict]]


@dataclass(frozen=True)
class RAGConfig:
    """RAG 파이프라인 설정

    각 도메인(법률, 보안 등)이 자신만의 설정을 정의하여 파이프라인에 주입한다.
    """

    system_prompt: str                    # LLM 시스템 프롬프트
    collections: list[CollectionConfig]   # 검색 대상 컬렉션 목록
    analyze_fn: Callable                  # 질의 분류 함수
    build_context_fns: dict[str, BuildContextFn] = field(default_factory=dict)
    extract_refs_fns: dict[str, ExtractRefsFn] = field(default_factory=dict)
    domain_name: str = "general"          # 로그 식별용 도메인 이름


# ---------------------------------------------------------------------------
# 기본 컨텍스트 빌더 / 참조 추출기
# ---------------------------------------------------------------------------

def _default_build_context(search_results: dict) -> str:
    """검색 결과를 LLM 컨텍스트 문자열로 변환 (기본 구현)"""
    if not search_results or not search_results.get("documents"):
        return "관련 자료를 찾을 수 없습니다."

    context_parts = []
    documents = search_results["documents"][0]
    metadatas = (
        search_results["metadatas"][0]
        if search_results.get("metadatas")
        else [{}] * len(documents)
    )

    for i, (doc, meta) in enumerate(zip(documents, metadatas)):
        source = meta.get("source", "알 수 없음")
        header = f"[참고자료 {i + 1}] 출처: {source}"
        context_parts.append(f"{header}\n{doc}\n")

    return "\n---\n".join(context_parts)


def _default_extract_references(search_results: dict) -> list[dict]:
    """검색 결과에서 참고 문헌 정보 추출 (기본 구현)"""
    if not search_results or not search_results.get("metadatas"):
        return []

    references = []
    for meta in search_results["metadatas"][0]:
        ref = {k: v for k, v in meta.items() if v}
        if ref:
            references.append(ref)
    return references


# ---------------------------------------------------------------------------
# 신뢰도 추정
# ---------------------------------------------------------------------------

def _estimate_confidence(search_results: dict, classification) -> ConfidenceLevel:
    """검색 결과와 분류 정보를 기반으로 답변 신뢰도를 추정한다."""
    if not search_results or not search_results.get("documents"):
        return ConfidenceLevel.LOW

    documents = search_results["documents"][0]
    distances = (
        search_results["distances"][0]
        if search_results.get("distances")
        else []
    )

    # 검색 결과가 적으면 신뢰도 낮음
    if len(documents) < 2:
        return ConfidenceLevel.LOW

    # 고위험 질의는 신뢰도 낮음
    if classification.is_high_risk:
        return ConfidenceLevel.LOW

    # 거리 기반 신뢰도 (ChromaDB는 거리가 작을수록 유사)
    if distances:
        avg_distance = sum(distances[:3]) / min(len(distances), 3)
        if avg_distance < _HIGH_CONFIDENCE_DISTANCE:
            return ConfidenceLevel.HIGH
        elif avg_distance < _MEDIUM_CONFIDENCE_DISTANCE:
            return ConfidenceLevel.MEDIUM

    return ConfidenceLevel.MEDIUM


# ---------------------------------------------------------------------------
# 동기 검색 헬퍼 (asyncio.to_thread 에서 실행)
# ---------------------------------------------------------------------------

def _search_collections(
    query: str,
    query_embedding: list[float],
    collections: list[CollectionConfig],
    classification,
) -> dict[str, dict]:
    """컬렉션별 벡터/하이브리드 검색을 수행한다 (동기).

    이벤트 루프를 블로킹하지 않도록 asyncio.to_thread()에서 호출된다.
    """
    vs = get_vector_store()
    search_results: dict[str, dict] = {}

    for col in collections:
        where_filter = col.build_where_fn(classification) if col.build_where_fn else None

        if col.enable_hybrid:
            fetch_n = col.n_results * col.retrieval_multiplier
            vector_results = vs.search(
                col.name, query_embedding, n_results=fetch_n, where=where_filter,
            )
            if where_filter and len(vector_results.get("ids", [[]])[0]) < 2:
                vector_results = vs.search(col.name, query_embedding, n_results=fetch_n)

            bm25_idx = get_bm25_index(col.name)
            bm25_results = bm25_idx.search(query, n_results=fetch_n)

            search_results[col.name] = reciprocal_rank_fusion(
                vector_results, bm25_results, top_k=col.n_results,
            )
        else:
            fetch_n = col.n_results * col.retrieval_multiplier
            raw_results = vs.search(
                col.name, query_embedding, n_results=fetch_n, where=where_filter,
            )
            if where_filter and len(raw_results.get("ids", [[]])[0]) < 2:
                raw_results = vs.search(col.name, query_embedding, n_results=fetch_n)

            search_results[col.name] = rerank_results(
                query, raw_results, top_k=col.n_results,
            )

    return search_results


# ---------------------------------------------------------------------------
# RAG 컨텍스트 준비 (공통 로직)
# ---------------------------------------------------------------------------

async def _prepare_rag_context(
    query: str,
    config: RAGConfig,
    session_messages: list[dict] | None = None,
) -> tuple:
    """RAG 컨텍스트를 준비하는 공통 로직.

    Returns:
        (classification, messages, {collection_name: search_results})
    """
    # 1. 질의 분석
    classification = config.analyze_fn(query)
    logger.info(
        f"{config.domain_name} 질의 분석 완료",
        category=(
            classification.category.value
            if hasattr(classification.category, "value")
            else str(classification.category)
        ),
        is_high_risk=classification.is_high_risk,
    )

    # 2. 질의 임베딩
    query_embedding = await embed_text(query)

    # 3. 벡터 검색 (메타데이터 필터링 + 리랭킹 + 하이브리드)
    # 동기 ChromaDB/BM25 호출을 별도 스레드에서 실행하여 이벤트 루프 블로킹 방지
    search_results = await asyncio.to_thread(
        _search_collections, query, query_embedding, config.collections, classification,
    )

    # 4. 컨텍스트 조합
    context_parts = []
    for col in config.collections:
        build_fn = config.build_context_fns.get(col.name, _default_build_context)
        ctx = build_fn(search_results[col.name])
        context_parts.append(f"## {col.label}\n{ctx}")
    context = "\n\n".join(context_parts)

    # 5. 메시지 구성
    messages: list[dict] = []
    if session_messages:
        messages.extend(session_messages)
    messages.append({
        "role": "user",
        "content": f"다음 참고 자료를 바탕으로 질문에 답변해주세요.\n\n{context}\n\n질문: {query}",
    })

    return classification, messages, search_results


# ---------------------------------------------------------------------------
# 공개 API — 일반 응답
# ---------------------------------------------------------------------------

async def rag_query(
    query: str,
    config: RAGConfig,
    session_messages: list[dict] | None = None,
) -> dict:
    """RAG 기반 Q&A — 일반(논스트리밍) 응답"""
    classification, messages, search_results = await _prepare_rag_context(
        query, config, session_messages,
    )

    # LLM 답변 생성
    client = get_llm_client()
    answer = await client.generate(
        system_prompt=config.system_prompt,
        messages=messages,
    )

    # 신뢰도 추정 (첫 번째 컬렉션 기준)
    primary_results = search_results[config.collections[0].name]
    confidence = _estimate_confidence(primary_results, classification)

    # 결과 구성
    result: dict = {
        "answer": answer,
        "confidence": confidence,
        "classification": classification,
    }
    for col in config.collections:
        extract_fn = config.extract_refs_fns.get(col.name, _default_extract_references)
        result[col.ref_key] = extract_fn(search_results[col.name])

    return result


# ---------------------------------------------------------------------------
# 공개 API — 스트리밍 응답
# ---------------------------------------------------------------------------

async def rag_query_stream(
    query: str,
    config: RAGConfig,
    session_messages: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """RAG 기반 Q&A — 스트리밍 응답"""
    classification, messages, search_results = await _prepare_rag_context(
        query, config, session_messages,
    )

    # 메타데이터 먼저 전송
    primary_results = search_results[config.collections[0].name]
    confidence = _estimate_confidence(primary_results, classification)

    metadata: dict = {
        "type": "metadata",
        "classification": classification.model_dump(),
        "confidence": confidence.value,
    }
    for col in config.collections:
        extract_fn = config.extract_refs_fns.get(col.name, _default_extract_references)
        metadata[col.ref_key] = extract_fn(search_results[col.name])
    yield metadata

    # LLM 스트리밍
    client = get_llm_client()
    async for chunk in client.generate_stream(
        system_prompt=config.system_prompt,
        messages=messages,
    ):
        yield {"type": "text", "content": chunk}

    yield {"type": "done"}
