"""
ChromaDB 벡터 스토어 관리 모듈
"""
import asyncio
import threading
import structlog
from chromadb import HttpClient
from chromadb.config import Settings as ChromaSettings

from config import settings

logger = structlog.get_logger(__name__)


class VectorStore:
    """ChromaDB 벡터 스토어 클라이언트"""

    def __init__(self) -> None:
        """ChromaDB HTTP 클라이언트 초기화"""
        self.client = HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info(
            "chromadb_client_initialized",
            host=settings.chroma_host,
            port=settings.chroma_port,
        )

    def get_collection(self, collection_name: str):
        """컬렉션 가져오기 또는 생성"""
        try:
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.debug("collection_retrieved", name=collection_name)
            return collection
        except Exception as e:
            logger.error(
                "collection_retrieval_failed",
                name=collection_name,
                error=str(e),
            )
            raise

    def add_documents(
        self,
        collection_name: str,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """문서를 컬렉션에 추가"""
        try:
            collection = self.get_collection(collection_name)

            if embeddings:
                collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                    embeddings=embeddings,
                )
            else:
                collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                )

            logger.info(
                "documents_added",
                collection=collection_name,
                count=len(documents),
            )
        except Exception as e:
            logger.error(
                "add_documents_failed",
                collection=collection_name,
                error=str(e),
            )
            raise

    def search(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int = 5,
        where: dict | None = None,
    ) -> dict:
        """임베딩 벡터로 유사 문서 검색"""
        try:
            collection = self.get_collection(collection_name)

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
            )

            logger.debug(
                "search_completed",
                collection=collection_name,
                n_results=n_results,
                found=len(results.get("ids", [[]])[0]),
            )

            return results
        except Exception as e:
            logger.error(
                "search_failed",
                collection=collection_name,
                error=str(e),
            )
            raise

    def delete_collection(self, collection_name: str) -> None:
        """컬렉션 삭제"""
        try:
            self.client.delete_collection(name=collection_name)
            logger.info("collection_deleted", name=collection_name)
        except Exception as e:
            logger.error(
                "delete_collection_failed",
                name=collection_name,
                error=str(e),
            )
            raise

    def get_collection_stats(self, collection_name: str) -> dict:
        """컬렉션 통계 조회"""
        try:
            collection = self.get_collection(collection_name)
            count = collection.count()

            stats = {
                "name": collection_name,
                "count": count,
                "metadata": collection.metadata,
            }

            logger.debug("collection_stats_retrieved", stats=stats)
            return stats
        except Exception as e:
            logger.error(
                "get_collection_stats_failed",
                name=collection_name,
                error=str(e),
            )
            raise

    async def async_search(self, collection_name, query_embedding, n_results=5, where=None):
        """비동기 벡터 검색"""
        return await asyncio.to_thread(
            self.search, collection_name, query_embedding, n_results, where
        )

    async def async_add_documents(self, collection_name, documents, embeddings, metadatas=None, ids=None):
        """비동기 문서 추가"""
        return await asyncio.to_thread(
            self.add_documents, collection_name, documents, embeddings, metadatas, ids
        )

    def upsert_documents(
        self,
        collection_name: str,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        """문서를 컬렉션에 upsert (동일 ID 존재 시 덮어쓰기)"""
        try:
            collection = self.get_collection(collection_name)
            kwargs = {
                "documents": documents,
                "metadatas": metadatas,
                "ids": ids,
            }
            if embeddings:
                kwargs["embeddings"] = embeddings
            collection.upsert(**kwargs)

            logger.info(
                "documents_upserted",
                collection=collection_name,
                count=len(documents),
            )
        except Exception as e:
            logger.error(
                "upsert_documents_failed",
                collection=collection_name,
                error=str(e),
            )
            raise

    def upsert_and_cleanup(
        self,
        collection_name: str,
        id_prefix: str,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
        embeddings: list[list[float]] | None = None,
    ) -> int:
        """upsert 후 이전 버전의 잔여 청크를 정리

        기존 delete → insert 방식과 달리, upsert를 먼저 수행하므로
        중간에 실패해도 기존 데이터가 유지됩니다.

        Args:
            collection_name: 컬렉션 이름
            id_prefix: 정리 대상 ID 프리픽스
            documents: 문서 텍스트 리스트
            metadatas: 메타데이터 리스트
            ids: 문서 ID 리스트
            embeddings: 임베딩 벡터 리스트

        Returns:
            삭제된 잔여 청크 수
        """
        # 1. 새 데이터 upsert (실패해도 기존 데이터 유지)
        self.upsert_documents(
            collection_name=collection_name,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

        # 2. upsert 성공 후 잔여 청크 삭제 (조문 수 감소 대응)
        new_id_set = set(ids)
        existing_ids = self.get_ids_by_prefix(collection_name, id_prefix)
        stale_ids = [id_ for id_ in existing_ids if id_ not in new_id_set]
        if stale_ids:
            self.delete_by_ids(collection_name, stale_ids)
            logger.info(
                "stale_chunks_cleaned",
                collection=collection_name,
                prefix=id_prefix,
                stale_count=len(stale_ids),
            )
        return len(stale_ids)

    async def async_upsert_and_cleanup(
        self,
        collection_name: str,
        id_prefix: str,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
        embeddings: list[list[float]] | None = None,
    ) -> int:
        """비동기 upsert + 잔여 청크 정리"""
        return await asyncio.to_thread(
            self.upsert_and_cleanup,
            collection_name, id_prefix, documents, metadatas, ids, embeddings,
        )

    def delete_by_ids(self, collection_name: str, ids: list[str]) -> None:
        """컬렉션에서 ID 목록으로 문서 삭제"""
        try:
            collection = self.get_collection(collection_name)
            collection.delete(ids=ids)
            logger.info(
                "documents_deleted_by_ids",
                collection=collection_name,
                count=len(ids),
            )
        except Exception as e:
            logger.error(
                "delete_by_ids_failed",
                collection=collection_name,
                error=str(e),
            )
            raise

    def update_metadatas(
        self,
        collection_name: str,
        ids: list[str],
        metadatas: list[dict],
    ) -> None:
        """컬렉션 내 문서 메타데이터 업데이트"""
        try:
            collection = self.get_collection(collection_name)
            collection.update(ids=ids, metadatas=metadatas)
            logger.info(
                "metadatas_updated",
                collection=collection_name,
                count=len(ids),
            )
        except Exception as e:
            logger.error(
                "update_metadatas_failed",
                collection=collection_name,
                error=str(e),
            )
            raise

    def get_ids_by_prefix(self, collection_name: str, prefix: str) -> list[str]:
        """컬렉션에서 ID 프리픽스로 매칭되는 ID 목록 조회"""
        try:
            collection = self.get_collection(collection_name)
            result = collection.get(include=[])
            all_ids = result.get("ids", [])
            matched = [id_ for id_ in all_ids if id_.startswith(prefix)]
            logger.debug(
                "ids_by_prefix",
                collection=collection_name,
                prefix=prefix,
                matched=len(matched),
            )
            return matched
        except Exception as e:
            logger.error(
                "get_ids_by_prefix_failed",
                collection=collection_name,
                prefix=prefix,
                error=str(e),
            )
            raise

    def delete_by_prefix(self, collection_name: str, id_prefix: str) -> int:
        """프리픽스에 매칭되는 문서를 일괄 삭제

        Args:
            collection_name: 컬렉션 이름
            id_prefix: 삭제할 ID 프리픽스

        Returns:
            삭제된 문서 수
        """
        matched_ids = self.get_ids_by_prefix(collection_name, id_prefix)
        if matched_ids:
            self.delete_by_ids(collection_name, matched_ids)
            logger.info(
                "documents_deleted_by_prefix",
                collection=collection_name,
                prefix=id_prefix,
                count=len(matched_ids),
            )
        return len(matched_ids)

    async def async_delete_by_prefix(self, collection_name: str, id_prefix: str) -> int:
        """비동기 프리픽스 기반 문서 삭제"""
        return await asyncio.to_thread(self.delete_by_prefix, collection_name, id_prefix)

    async def async_delete_by_ids(self, collection_name: str, ids: list[str]) -> None:
        """비동기 ID 기반 문서 삭제"""
        return await asyncio.to_thread(self.delete_by_ids, collection_name, ids)

    async def async_update_metadatas(
        self, collection_name: str, ids: list[str], metadatas: list[dict]
    ) -> None:
        """비동기 메타데이터 업데이트"""
        return await asyncio.to_thread(
            self.update_metadatas, collection_name, ids, metadatas
        )

    async def async_get_ids_by_prefix(self, collection_name: str, prefix: str) -> list[str]:
        """비동기 프리픽스 기반 ID 조회"""
        return await asyncio.to_thread(self.get_ids_by_prefix, collection_name, prefix)


# 싱글톤 인스턴스
_vector_store_instance: "VectorStore | None" = None
_lock = threading.Lock()


def get_vector_store() -> VectorStore:
    """VectorStore 싱글톤 인스턴스 반환"""
    global _vector_store_instance
    if _vector_store_instance is None:
        with _lock:
            if _vector_store_instance is None:
                _vector_store_instance = VectorStore()
    return _vector_store_instance
