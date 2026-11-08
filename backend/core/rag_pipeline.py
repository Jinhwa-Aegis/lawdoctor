"""제네릭 RAG 파이프라인 — 벡터 검색 → 컨텍스트 조합 → LLM 답변 생성

법률 RAG(core.rag)와 보안 RAG(core.security_rag)의 공통 로직을 통합한다.
각 도메인은 RAGConfig를 통해 컬렉션, 시스템 프롬프트, 컨텍스트 빌더,
참조 추출기 등을 주입하여 동작을 커스터마이즈한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import AsyncGenerator, Callable

import asyncio

import structlog

from core.citation_verifier import verify_citations
from core.confidence import combine_confidence, parse_stated_confidence
from core.embeddings import embed_text
from core.followups import generate_followups
from core.multi_perspective import (
    PerspectiveConfig,
    append_unique,
    filter_by_sources,
    coordinator_prompt,
    coordinator_user_message,
    make_domain_classification,
    merge_balanced,
    opinions_text,
    run_experts,
    select_domains,
)
from core.hybrid_search import get_bm25_index, reciprocal_rank_fusion
from core.llm import get_llm_client
from core.multihop import plan_multihop
from core.query_rewriter import rewrite_query
from core.reranker import rerank_results
from data.law_api import article_label
from data.vector_store import get_vector_store
from models.chat import ConfidenceLevel

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# 신뢰도 임계값 상수
# ---------------------------------------------------------------------------
_HIGH_CONFIDENCE_DISTANCE = 0.3
_MEDIUM_CONFIDENCE_DISTANCE = 0.6

# 답변 후처리 시간 제한 (초) — 개별 법령 조회는 citation_verifier에서 별도 제한
_VERIFY_TIMEOUT_SECONDS = 15.0
_FOLLOWUP_TIMEOUT_SECONDS = 10.0


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
    enable_query_rewrite: bool = True     # 질의 재작성 활성화
    enable_multihop: bool = False         # 멀티홉 추론 활성화
    enable_citation_verification: bool = False  # 답변 내 법령 인용 실존 검증
    enable_followups: bool = True               # 후속 질문 추천
    expand_query_fn: Callable[[str], str] | None = None  # 검색 질의 보강 (일상어 → 법령 용어)
    perspective: PerspectiveConfig | None = None         # 분야 간 의견 대조 (복수 분야 질의)
    concept_queries_fn: Callable[[str], list[str]] | None = None  # 법령 개념별 추가 검색
    concept_collection: str = "laws"                     # 개념 검색 대상 컬렉션
    concept_top_k: int = 2                               # 개념마다 보탤 조문 수


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
# 인용 헬퍼
# ---------------------------------------------------------------------------

def _format_citation_header(meta: dict, idx: int) -> str:
    """메타데이터로부터 인용 헤더를 구성한다 (도메인 자동 감지)."""
    source_type = meta.get("source_type", "")
    header = f"[{idx}]"

    if source_type == "precedent":
        name = meta.get("case_name", "")
        court = meta.get("court", "")
        case_num = meta.get("case_number", "")
        header += f" 판례: {name}"
        if court:
            header += f" ({court}"
            if case_num:
                header += f" {case_num}"
            header += ")"
    elif source_type == "law":
        law_name = meta.get("law_name", meta.get("source", ""))
        art_num = meta.get("article_number", "")
        art_title = meta.get("article_title", "")
        header += f" 법령: {law_name}"
        if art_num:
            header += f" {article_label(art_num)}"
        if art_title:
            header += f" ({art_title})"
    elif meta.get("guide_name"):
        header += f" {meta['guide_name']}"
        if meta.get("standard"):
            header += f" ({meta['standard']})"
        if meta.get("section"):
            header += f" — {meta['section']}"
    elif source_type == "consultation":
        header += f" 자문: {meta.get('source', '자문 이력')}"
    else:
        header += f" {meta.get('source', '참고자료')}"

    return header


def _build_citation(meta: dict, doc: str, idx: int) -> dict:
    """검색 결과 1건으로부터 인용 정보 딕셔너리를 구성한다."""
    # 발췌: 컨텍스트 프리픽스(【...】) 제거 후 앞부분 발췌
    excerpt = doc or ""
    if excerpt.startswith("【"):
        nl = excerpt.find("\n")
        if nl > 0:
            excerpt = excerpt[nl + 1:]
    excerpt = excerpt.strip()
    if len(excerpt) > 300:
        excerpt = excerpt[:300] + "…"

    source_type = meta.get("source_type", "")

    citation: dict = {
        "citation_id": idx,
        "source_type": source_type,
        "source": meta.get("source", ""),
        "excerpt": excerpt,
    }

    if source_type == "law":
        citation.update({
            "law_name": meta.get("law_name", meta.get("source", "")),
            "article_number": meta.get("article_number", ""),
            "article_title": meta.get("article_title", ""),
        })
    elif source_type == "precedent":
        citation.update({
            "case_name": meta.get("case_name", ""),
            "case_number": meta.get("case_number", ""),
            "court": meta.get("court", ""),
            "decision_date": meta.get("decision_date", ""),
        })
    elif meta.get("guide_name"):
        citation.update({
            "guide_name": meta.get("guide_name", ""),
            "standard": meta.get("standard", ""),
            "section": meta.get("section", ""),
        })

    return citation


# ---------------------------------------------------------------------------
# RAG 컨텍스트 준비 (공통 로직)
# ---------------------------------------------------------------------------

async def _prepare_multihop_context(
    query: str,
    config: RAGConfig,
    classification,
    multihop_plan,
    search_query: str,
) -> dict[str, dict]:
    """멀티홉 질의의 하위 질문별 병렬 검색 및 결과 통합.

    각 sub_query를 병렬로 임베딩·검색한 후 document ID 기반 중복 제거 후
    통합 결과에 리랭킹을 적용한다.
    """
    from core.reranker import rerank_results as _rerank

    async def _search_sub(sub_query_text: str) -> dict[str, dict]:
        emb = await embed_text(sub_query_text)
        return await asyncio.to_thread(
            _search_collections, sub_query_text, emb, config.collections, classification,
        )

    # 병렬 실행
    sub_results_list = await asyncio.gather(
        *[_search_sub(sq.query) for sq in multihop_plan.sub_queries]
    )

    # 컬렉션별 결과 통합 (document ID 기반 중복 제거)
    merged: dict[str, dict] = {}
    for col in config.collections:
        seen_ids: set[str] = set()
        all_docs, all_metas, all_ids, all_dists = [], [], [], []

        for sub_res in sub_results_list:
            col_res = sub_res.get(col.name, {})
            ids_list = col_res.get("ids", [[]])[0]
            docs_list = col_res.get("documents", [[]])[0]
            metas_list = (col_res.get("metadatas", [[]])[0] if col_res.get("metadatas") else [{}] * len(docs_list))
            dists_list = (col_res.get("distances", [[]])[0] if col_res.get("distances") else [0.0] * len(docs_list))

            for doc_id, doc, meta, dist in zip(ids_list, docs_list, metas_list, dists_list):
                if doc_id not in seen_ids:
                    seen_ids.add(doc_id)
                    all_ids.append(doc_id)
                    all_docs.append(doc)
                    all_metas.append(meta)
                    all_dists.append(dist)

        raw_merged = {
            "ids": [all_ids],
            "documents": [all_docs],
            "metadatas": [all_metas],
            "distances": [all_dists],
        }

        # 통합 결과에 리랭킹 적용
        merged[col.name] = _rerank(search_query, raw_merged, top_k=col.n_results)

    return merged


def apply_category_override(classification, category):
    """사용자가 직접 고른 분야로 주 분야를 바꾼다. 원래 분류된 분야는 관련 분야로 남긴다."""
    if category is None or classification.category == category:
        return classification
    related = [c for c in getattr(classification, "related_categories", []) if c != category]
    if classification.category not in related:
        related.insert(0, classification.category)
    return classification.model_copy(update={"category": category, "related_categories": related})


async def _prepare_rag_context(
    query: str,
    config: RAGConfig,
    session_messages: list[dict] | None = None,
    category_override=None,
) -> tuple:
    """RAG 컨텍스트를 준비하는 공통 로직.

    Returns:
        (classification, messages, {collection_name: search_results})
    """
    # 1. 질의 분석
    classification = apply_category_override(config.analyze_fn(query), category_override)
    logger.info(
        f"{config.domain_name} 질의 분석 완료",
        category=(
            classification.category.value
            if hasattr(classification.category, "value")
            else str(classification.category)
        ),
        is_high_risk=classification.is_high_risk,
    )

    # 2. 질의 재작성 (활성화 시)
    search_query = query
    rewrite_info = None
    if config.enable_query_rewrite:
        rewrite_info = await rewrite_query(query, session_messages)
        search_query = rewrite_info.rewritten
        if rewrite_info.was_rewritten:
            logger.info(
                "질의 재작성 적용",
                original=query,
                rewritten=search_query,
            )

    # 2-1. 검색 질의 보강 (분류·LLM 질문에는 원문 사용)
    if config.expand_query_fn:
        expanded = config.expand_query_fn(search_query)
        if expanded != search_query:
            logger.info("검색 질의 법령 용어 보강", original=search_query, expanded=expanded)
            search_query = expanded

    # 3. 멀티홉 판단 (활성화 시)
    multihop_plan = None
    if config.enable_multihop:
        multihop_plan = await plan_multihop(search_query, classification)

    # 4. 검색 수행
    if multihop_plan and multihop_plan.needs_multihop:
        # 멀티홉: 각 sub_query 병렬 검색 → 결과 통합
        logger.info(
            "멀티홉 검색 수행",
            sub_query_count=len(multihop_plan.sub_queries),
        )
        search_results = await _prepare_multihop_context(
            query, config, classification, multihop_plan, search_query,
        )
    else:
        # 단일 검색: 재작성 질의 임베딩 → 검색
        query_embedding = await embed_text(search_query)
        search_results = await asyncio.to_thread(
            _search_collections, search_query, query_embedding,
            config.collections, classification,
        )

    # 4-1. 분야 간 의견 대조 대상이면 분야별로 법령을 나눠 검색해 균형 있게 합친다
    domains = (
        select_domains(classification, config.perspective, category_override)
        if config.perspective else []
    )
    if domains:
        law_col = next(
            (c for c in config.collections if c.name == config.perspective.law_collection), None,
        )
        if law_col:
            pcfg = config.perspective
            # 같은 조문의 여러 청크를 걸러낸 뒤에도 조문이 충분하도록 후보를 넉넉히 가져온다
            fetch_col = replace(law_col, n_results=pcfg.per_domain_fetch)
            domain_embedding = await embed_text(search_query)
            per_domain = await asyncio.gather(*[
                asyncio.to_thread(
                    _search_collections, search_query, domain_embedding, [fetch_col],
                    make_domain_classification(classification, d),
                )
                for d in domains
            ])
            search_results[law_col.name] = merge_balanced(
                [
                    filter_by_sources(r[law_col.name], pcfg.domain_sources.get(d, []))
                    for d, r in zip(domains, per_domain)
                ],
                limit=pcfg.per_domain_results * len(domains),
                per_domain_limit=pcfg.per_domain_results,
            )
            logger.info("분야별 균형 검색", domains=[str(d) for d in domains])

    # 4-2. 개념 검색: 질의 속 일상어에 대응하는 법령 개념으로 따로 검색해 근거를 보탠다
    #      (질문의 지배적인 단어에 가려 두 번째 쟁점의 조문이 빠지는 것을 막는다)
    concepts = config.concept_queries_fn(query) if config.concept_queries_fn else []
    concept_col = next((c for c in config.collections if c.name == config.concept_collection), None)
    if concepts and concept_col and concept_col.name in search_results:
        vs = get_vector_store()
        concept_embeddings = await asyncio.gather(*[embed_text(c) for c in concepts])
        concept_results = await asyncio.gather(*[
            asyncio.to_thread(vs.search, concept_col.name, emb, config.concept_top_k + 3)
            for emb in concept_embeddings
        ])
        search_results[concept_col.name] = append_unique(
            search_results[concept_col.name], concept_results, per_extra=config.concept_top_k,
        )
        logger.info("개념 검색 보강", concepts=concepts)

    # 5. 글로벌 인용 번호 부여 + 컨텍스트 조합
    context_parts = []
    all_citations: list[dict] = []
    citation_idx = 1

    if multihop_plan and multihop_plan.needs_multihop:
        sub_info = "\n".join(
            f"- {sq.query} ({sq.purpose})"
            for sq in multihop_plan.sub_queries
        )
        context_parts.append(f"## 질의 분해\n{sub_info}")

    for col in config.collections:
        col_results = search_results.get(col.name, {})
        docs = col_results.get("documents", [[]])[0] if col_results else []
        metas = (
            col_results.get("metadatas", [[]])[0]
            if col_results and col_results.get("metadatas")
            else [{}] * len(docs)
        )

        if not docs:
            context_parts.append(f"## {col.label}\n관련 자료를 찾을 수 없습니다.")
            continue

        col_context = []
        for doc, meta in zip(docs, metas):
            header = _format_citation_header(meta, citation_idx)
            col_context.append(f"{header}\n{doc}\n")

            citation = _build_citation(meta, doc, citation_idx)
            all_citations.append(citation)
            citation_idx += 1

        context_parts.append(f"## {col.label}\n" + "\n---\n".join(col_context))

    context = "\n\n".join(context_parts)

    # 6. 메시지 구성 (원본 질의 사용, 인라인 인용 지시)
    messages: list[dict] = []
    if session_messages:
        messages.extend(session_messages)
    messages.append({
        "role": "user",
        "content": (
            "다음 참고 자료를 바탕으로 질문에 답변해주세요.\n"
            "답변 본문에서 참고 자료를 인용할 때 반드시 [1], [2] 등의 번호를 "
            "해당 문장 끝에 표시하세요.\n\n"
            f"{context}\n\n질문: {query}"
        ),
    })

    return classification, messages, search_results, all_citations, context, domains


async def _apply_perspectives(query, config, context, domains, messages):
    """분야별 검토를 실행하고, 종합 답변용 시스템 프롬프트·메시지를 만든다.

    Returns:
        (opinions, system_prompt, messages)
    """
    opinions = await run_experts(query, context, domains, config.perspective)
    if len(opinions) < 2:  # 한 분야만 성공하면 일반 답변으로 진행
        return opinions, config.system_prompt, messages
    messages = [*messages[:-1], {
        **messages[-1], "content": coordinator_user_message(messages[-1]["content"], opinions),
    }]
    return opinions, coordinator_prompt(config.system_prompt, opinions), messages


# ---------------------------------------------------------------------------
# 답변 후처리 — 인용 검증 + 후속 질문 (병렬)
# ---------------------------------------------------------------------------

async def _post_process_answer(
    query: str,
    answer: str,
    config: RAGConfig,
    retrieval_confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
    extra_verify_text: str = "",
) -> dict:
    """답변 생성 후 인용 검증과 후속 질문 생성을 병렬로 수행한다.

    어느 한쪽이 실패해도 나머지 결과는 반환한다.

    Returns:
        {"verified_citations": list[dict], "followups": list[str]}
    """
    async def _noop() -> list:
        return []

    async def _bounded(coro, timeout: float, name: str) -> list:
        """시간 제한 초과 시 빈 결과 — 답변 저장(done)이 늦어지지 않게 한다."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("후처리 시간 초과", task=name, timeout=timeout)
            return []

    verify_task = (
        _bounded(
            verify_citations(f"{answer}\n{extra_verify_text}" if extra_verify_text else answer),
            _VERIFY_TIMEOUT_SECONDS, "citation_verification",
        )
        if config.enable_citation_verification else _noop()
    )
    followup_task = (
        _bounded(
            generate_followups(query, answer, domain=config.domain_name),
            _FOLLOWUP_TIMEOUT_SECONDS, "followups",
        )
        if config.enable_followups else _noop()
    )
    verified, followups = await asyncio.gather(
        verify_task, followup_task, return_exceptions=True,
    )

    if isinstance(verified, BaseException):
        logger.warning("인용 검증 실패", error=str(verified))
        verified = []
    if isinstance(followups, BaseException):
        logger.warning("후속 질문 생성 실패", error=str(followups))
        followups = []

    # 최종 신뢰도 = min(검색 근거, AI 자체 평가, 인용 검증 결과)
    stated, reason = parse_stated_confidence(answer)
    final, adjustments = combine_confidence(retrieval_confidence, stated, verified)

    return {
        "verified_citations": verified,
        "followups": followups,
        "confidence": final.value,
        "confidence_reason": reason,
        "confidence_adjustments": adjustments,
    }


# ---------------------------------------------------------------------------
# 공개 API — 일반 응답
# ---------------------------------------------------------------------------

async def rag_query(
    query: str,
    config: RAGConfig,
    session_messages: list[dict] | None = None,
    category_override=None,
) -> dict:
    """RAG 기반 Q&A — 일반(논스트리밍) 응답"""
    classification, messages, search_results, citations, context, domains = await _prepare_rag_context(
        query, config, session_messages, category_override,
    )

    # 분야 간 의견 대조 (복수 분야 질의)
    opinions: list[dict] = []
    system_prompt = config.system_prompt
    if domains:
        opinions, system_prompt, messages = await _apply_perspectives(
            query, config, context, domains, messages,
        )

    # LLM 답변 생성
    client = get_llm_client()
    answer = await client.generate(
        system_prompt=system_prompt,
        messages=messages,
    )

    # 신뢰도 추정 (첫 번째 컬렉션 기준)
    primary_results = search_results[config.collections[0].name]
    confidence = _estimate_confidence(primary_results, classification)

    # 결과 구성
    answer_meta = await _post_process_answer(
        query, answer, config, confidence, extra_verify_text=opinions_text(opinions),
    )
    if opinions:
        answer_meta["perspectives"] = opinions
    result: dict = {
        "answer": answer,
        "confidence": ConfidenceLevel(answer_meta["confidence"]),
        "classification": classification,
        "citations": citations,
        "answer_meta": answer_meta,
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
    category_override=None,
) -> AsyncGenerator[dict, None]:
    """RAG 기반 Q&A — 스트리밍 응답"""
    classification, messages, search_results, citations, context, domains = await _prepare_rag_context(
        query, config, session_messages, category_override,
    )

    # 메타데이터 먼저 전송
    primary_results = search_results[config.collections[0].name]
    confidence = _estimate_confidence(primary_results, classification)

    metadata: dict = {
        "type": "metadata",
        "classification": classification.model_dump(),
        "confidence": confidence.value,
        "citations": citations,
        "perspective_domains": [config.perspective.labels[d] for d in domains] if domains else [],
    }
    for col in config.collections:
        extract_fn = config.extract_refs_fns.get(col.name, _default_extract_references)
        metadata[col.ref_key] = extract_fn(search_results[col.name])
    yield metadata

    # 분야 간 의견 대조 (복수 분야 질의) — 분야별 검토 결과를 먼저 보낸다
    opinions: list[dict] = []
    system_prompt = config.system_prompt
    if domains:
        yield {"type": "status", "stage": "perspectives"}
        opinions, system_prompt, messages = await _apply_perspectives(
            query, config, context, domains, messages,
        )
        yield {"type": "perspectives", "items": opinions}

    # LLM 스트리밍
    client = get_llm_client()
    full_answer = ""
    async for chunk in client.generate_stream(
        system_prompt=system_prompt,
        messages=messages,
    ):
        full_answer += chunk
        yield {"type": "text", "content": chunk}

    # 후처리 결과(인용 검증 + 후속 질문)를 done 직전에 전송
    if config.enable_citation_verification or config.enable_followups:
        yield {"type": "status", "stage": "post_processing"}
    answer_meta = await _post_process_answer(
        query, full_answer, config, confidence, extra_verify_text=opinions_text(opinions),
    )
    if opinions:
        answer_meta["perspectives"] = opinions
    yield {"type": "answer_meta", **answer_meta}

    yield {"type": "done"}
