"""하이브리드 검색 모듈 — BM25 + 벡터 검색을 RRF로 융합

BM25 키워드 검색과 벡터 의미 검색을 Reciprocal Rank Fusion(RRF)으로 결합하여
법률 조문 번호 등 정확한 키워드 매칭이 필요한 경우의 리콜을 향상시킨다.
"""

from __future__ import annotations

import threading
from typing import Any

import structlog
from rank_bm25 import BM25Okapi

from data.vector_store import get_vector_store

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# 한국어 토크나이저 (BM25용)
# ---------------------------------------------------------------------------

def _tokenize_korean_for_bm25(text: str) -> list[str]:
    """공백 분리 + 2/3-gram 문자 토큰을 생성한다.

    한국어는 형태소 분석 없이도 n-gram으로 적절한 BM25 성능을 얻을 수 있다.
    """
    tokens = []
    for word in text.split():
        word = word.strip(".,;:!?\"'()[]{}~`")
        if not word:
            continue
        tokens.append(word)
        # 2-gram, 3-gram 문자 토큰
        for n in (2, 3):
            for i in range(len(word) - n + 1):
                tokens.append(word[i : i + n])
    return tokens


# ---------------------------------------------------------------------------
# BM25 인덱스
# ---------------------------------------------------------------------------

class BM25Index:
    """단일 ChromaDB 컬렉션에 대한 BM25 인덱스"""

    def __init__(self, collection_name: str) -> None:
        self.collection_name = collection_name
        self._bm25: BM25Okapi | None = None
        self._doc_ids: list[str] = []
        self._documents: list[str] = []
        self._metadatas: list[dict] = []

    def build(self) -> None:
        """ChromaDB 컬렉션의 전체 문서로 BM25 인덱스를 빌드한다."""
        vs = get_vector_store()
        collection = vs.get_collection(self.collection_name)
        data = collection.get(include=["documents", "metadatas"])

        self._doc_ids = data.get("ids", [])
        self._documents = data.get("documents", [])
        self._metadatas = data.get("metadatas", []) or [{}] * len(self._doc_ids)

        if not self._documents:
            logger.warning("bm25_empty_collection", collection=self.collection_name)
            self._bm25 = None
            return

        tokenized = [_tokenize_korean_for_bm25(doc) for doc in self._documents]
        self._bm25 = BM25Okapi(tokenized)

        logger.info(
            "bm25_index_built",
            collection=self.collection_name,
            doc_count=len(self._documents),
        )

    def search(self, query: str, n_results: int = 10) -> dict:
        """BM25 스코어 기반 검색. ChromaDB query() 호환 형식으로 반환한다."""
        if self._bm25 is None or not self._documents:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        tokenized_query = _tokenize_korean_for_bm25(query)
        scores = self._bm25.get_scores(tokenized_query)

        if len(scores) == 0:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        # 상위 n_results 인덱스 (점수 내림차순)
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[
            :n_results
        ]

        ids = [self._doc_ids[i] for i in ranked_indices]
        documents = [self._documents[i] for i in ranked_indices]
        metadatas = [self._metadatas[i] for i in ranked_indices]
        # BM25 점수를 거리 형식으로 변환 (높은 점수 → 낮은 거리)
        score_max = max(scores)
        max_score = score_max if score_max > 0 else 1.0
        distances = [1.0 - scores[i] / max_score for i in ranked_indices]

        return {
            "ids": [ids],
            "documents": [documents],
            "metadatas": [metadatas],
            "distances": [distances],
        }


# ---------------------------------------------------------------------------
# 싱글톤 인덱스 관리
# ---------------------------------------------------------------------------

_bm25_indices: dict[str, BM25Index] = {}
_lock = threading.Lock()


def get_bm25_index(collection_name: str) -> BM25Index:
    """BM25 인덱스 싱글톤을 반환한다. 없으면 지연 빌드한다."""
    if collection_name not in _bm25_indices:
        with _lock:
            if collection_name not in _bm25_indices:
                idx = BM25Index(collection_name)
                idx.build()
                _bm25_indices[collection_name] = idx
    return _bm25_indices[collection_name]


def rebuild_bm25_index(collection_name: str) -> None:
    """데이터 변경 후 BM25 인덱스를 재빌드한다."""
    with _lock:
        idx = BM25Index(collection_name)
        idx.build()
        _bm25_indices[collection_name] = idx
    logger.info("bm25_index_rebuilt", collection=collection_name)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    vector_results: dict,
    bm25_results: dict,
    top_k: int = 5,
    k: int = 60,
) -> dict:
    """벡터 검색 결과와 BM25 검색 결과를 RRF 공식으로 융합한다.

    RRF score = sum(1 / (k + rank_i)) for each ranking list i

    Args:
        vector_results: 벡터 검색 ChromaDB 형식 결과
        bm25_results: BM25 검색 ChromaDB 형식 결과
        top_k: 반환할 상위 결과 수
        k: RRF 파라미터 (기본 60)

    Returns:
        융합된 ChromaDB 형식 결과
    """
    # 문서 정보를 ID 기준으로 수집
    doc_info: dict[str, dict[str, Any]] = {}

    def _collect(results: dict, source: str) -> list[str]:
        """결과에서 순위별 ID 목록을 추출하고 문서 정보를 수집한다."""
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            if doc_id not in doc_info:
                doc_info[doc_id] = {
                    "document": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "distance": distances[i] if i < len(distances) else 1.0,
                    "rrf_score": 0.0,
                }
        return ids

    vector_ids = _collect(vector_results, "vector")
    bm25_ids = _collect(bm25_results, "bm25")

    # RRF 점수 계산
    for rank, doc_id in enumerate(vector_ids):
        doc_info[doc_id]["rrf_score"] += 1.0 / (k + rank + 1)
    for rank, doc_id in enumerate(bm25_ids):
        doc_info[doc_id]["rrf_score"] += 1.0 / (k + rank + 1)

    # RRF 점수 내림차순 정렬
    sorted_ids = sorted(doc_info.keys(), key=lambda x: doc_info[x]["rrf_score"], reverse=True)
    top_ids = sorted_ids[:top_k]

    result = {
        "ids": [[did for did in top_ids]],
        "documents": [[doc_info[did]["document"] for did in top_ids]],
        "metadatas": [[doc_info[did]["metadata"] for did in top_ids]],
        "distances": [[doc_info[did]["distance"] for did in top_ids]],
    }

    logger.debug(
        "rrf_completed",
        vector_count=len(vector_ids),
        bm25_count=len(bm25_ids),
        unique_count=len(doc_info),
        output_count=len(top_ids),
    )

    return result
