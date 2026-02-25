"""
OpenAI 임베딩 생성 모듈
"""
import asyncio

import structlog
from openai import AsyncOpenAI

from config import settings

logger = structlog.get_logger(__name__)

# OpenAI 비동기 클라이언트 (지연 초기화)
_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def embed_text(text: str) -> list[float]:
    """
    단일 텍스트를 임베딩 벡터로 변환

    Args:
        text: 임베딩할 텍스트

    Returns:
        임베딩 벡터 (1536차원)
    """
    try:
        response = await _get_openai_client().embeddings.create(
            model=settings.embedding_model,
            input=text,
        )

        embedding = response.data[0].embedding

        logger.debug(
            "text_embedded",
            text_length=len(text),
            embedding_dim=len(embedding),
        )

        return embedding
    except Exception as e:
        logger.error(
            "embed_text_failed",
            text_preview=text[:100],
            error=str(e),
        )
        raise


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    여러 텍스트를 배치로 임베딩 (1000개씩 청크 처리)

    Args:
        texts: 임베딩할 텍스트 리스트

    Returns:
        임베딩 벡터 리스트
    """
    if not texts:
        return []

    chunk_size = 1000
    all_embeddings: list[list[float]] = []

    try:
        # 1000개씩 청크로 분할
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i:i + chunk_size]

            logger.debug(
                "embedding_chunk",
                chunk_index=i // chunk_size,
                chunk_size=len(chunk),
                total=len(texts),
            )

            response = await _get_openai_client().embeddings.create(
                model=settings.embedding_model,
                input=chunk,
            )

            chunk_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(chunk_embeddings)

            # API 레이트 리밋 방지를 위한 짧은 대기
            if i + chunk_size < len(texts):
                await asyncio.sleep(0.1)

        logger.info(
            "batch_embedding_completed",
            total_texts=len(texts),
            total_embeddings=len(all_embeddings),
        )

        return all_embeddings
    except Exception as e:
        logger.error(
            "embed_batch_failed",
            total_texts=len(texts),
            error=str(e),
        )
        raise


async def embed_documents(
    documents: list[dict],
    text_field: str = "content",
) -> list[list[float]]:
    """
    문서 리스트에서 특정 필드를 추출하여 배치 임베딩

    Args:
        documents: 문서 딕셔너리 리스트
        text_field: 임베딩할 텍스트가 있는 필드명

    Returns:
        임베딩 벡터 리스트
    """
    texts = [doc.get(text_field, "") for doc in documents]
    return await embed_batch(texts)
