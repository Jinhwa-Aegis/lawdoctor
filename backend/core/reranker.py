"""키워드 리랭킹 모듈

벡터 거리 점수와 키워드 오버랩 점수를 결합하여 검색 결과를 재정렬한다.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# 한국어 일반 조사 패턴 (2~3글자)
_KOREAN_JOSA = re.compile(
    r"(은|는|이|가|을|를|의|에|에서|도|로|으로|와|과|하고|이나|거나|든지|만|까지|부터|라도|조차|마저|뿐)$"
)


def _tokenize_korean(text: str) -> set[str]:
    """한국어 텍스트를 공백 분리 후 조사를 제거한 토큰 집합으로 변환한다."""
    tokens = set()
    for word in text.split():
        word = word.strip(".,;:!?\"'()[]{}~`")
        if not word:
            continue
        # 조사 제거
        stripped = _KOREAN_JOSA.sub("", word)
        if stripped:
            tokens.add(stripped)
        tokens.add(word)
    return tokens


def compute_keyword_score(query: str, document: str) -> float:
    """쿼리와 문서 간 키워드 오버랩 점수를 계산한다 (0~1)."""
    query_tokens = _tokenize_korean(query)
    if not query_tokens:
        return 0.0
    doc_tokens = _tokenize_korean(document)
    overlap = query_tokens & doc_tokens
    return len(overlap) / len(query_tokens)


def rerank_results(
    query: str,
    search_results: dict,
    top_k: int = 5,
    distance_weight: float = 0.6,
    keyword_weight: float = 0.4,
) -> dict:
    """벡터 거리 + 키워드 매칭 가중 결합으로 검색 결과를 리랭킹한다.

    Args:
        query: 사용자 질의
        search_results: ChromaDB query() 반환 형식 dict
        top_k: 반환할 상위 결과 수
        distance_weight: 벡터 유사도 점수 가중치
        keyword_weight: 키워드 오버랩 점수 가중치

    Returns:
        리랭킹된 ChromaDB 형식 dict
    """
    if not search_results or not search_results.get("ids"):
        return search_results

    ids = search_results["ids"][0]
    if not ids:
        return search_results

    documents = search_results.get("documents", [[]])[0]
    metadatas = search_results.get("metadatas", [[]])[0]
    distances = search_results.get("distances", [[]])[0]

    # 거리를 유사도 점수로 변환 (cosine 거리: 0이 가장 유사, 2가 최대)
    # score = 1 - distance/2 → 0~1 범위
    scored = []
    for i, (doc_id, doc, meta, dist) in enumerate(zip(ids, documents, metadatas, distances)):
        similarity = max(0.0, 1.0 - dist / 2.0)
        kw_score = compute_keyword_score(query, doc)
        combined = distance_weight * similarity + keyword_weight * kw_score
        scored.append((combined, i, doc_id, doc, meta, dist))

    # 결합 점수 내림차순 정렬
    scored.sort(key=lambda x: x[0], reverse=True)

    # 상위 top_k개 선택
    top = scored[:top_k]

    result = {
        "ids": [[t[2] for t in top]],
        "documents": [[t[3] for t in top]],
        "metadatas": [[t[4] for t in top]],
        "distances": [[t[5] for t in top]],
    }

    logger.debug(
        "rerank_completed",
        query_len=len(query),
        input_count=len(ids),
        output_count=len(top),
    )

    return result
