"""시맨틱 청킹 — 문서 유형별 의미 단위 분할

법령(law), 판례(precedent), 자문(consultation) 유형에 따라
의미 경계에서 텍스트를 분할하여 RAG 검색 품질을 높인다.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# 공통 상수
# ---------------------------------------------------------------------------
_DEFAULT_MAX_CHUNK = 1200
_DEFAULT_MIN_CHUNK = 200

# 문장 경계 패턴 (추가 분할 시 사용)
_SENTENCE_BOUNDARY = re.compile(r"(?<=\.)\s+|(?<=\.)\n|(?<=다\.)\s*|(?<=요\.)\s*")


# ---------------------------------------------------------------------------
# 유틸리티
# ---------------------------------------------------------------------------

def _split_at_sentence(text: str, max_size: int) -> list[str]:
    """max_size 초과 텍스트를 문장 경계에서 분할한다."""
    if len(text) <= max_size:
        return [text]

    parts: list[str] = []
    current = ""

    for sentence in _SENTENCE_BOUNDARY.split(text):
        if not sentence.strip():
            continue
        if current and len(current) + len(sentence) + 1 > max_size:
            parts.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        parts.append(current.strip())

    # 분할 후에도 초과하는 청크가 있으면 강제 분할
    final: list[str] = []
    for p in parts:
        if len(p) > max_size:
            for i in range(0, len(p), max_size):
                chunk = p[i : i + max_size].strip()
                if chunk:
                    final.append(chunk)
        else:
            final.append(p)

    return final


def _merge_small_chunks(
    chunks: list[str], min_size: int
) -> list[str]:
    """min_size 미만 청크를 이전 청크에 병합한다."""
    if not chunks:
        return chunks

    merged: list[str] = [chunks[0]]
    for chunk in chunks[1:]:
        if len(chunk) < min_size and merged:
            merged[-1] = f"{merged[-1]}\n{chunk}"
        else:
            merged.append(chunk)

    return merged


# ---------------------------------------------------------------------------
# 법령 청킹: 항(①②③) 단위 분할
# ---------------------------------------------------------------------------

# 항 번호 패턴: ① ② ③ ... 또는 유니코드 원문자
_PARAGRAPH_MARKER = re.compile(r"(?=[\u2460-\u2473\u3251-\u325F])")


def _chunk_law(text: str, max_size: int, min_size: int) -> list[str]:
    """법령 조문을 항(①②③) 경계에서 분할한다."""
    # 항 번호가 없으면 문장 경계로 분할
    if not _PARAGRAPH_MARKER.search(text):
        return _split_at_sentence(text, max_size)

    raw_parts = _PARAGRAPH_MARKER.split(text)
    raw_parts = [p for p in raw_parts if p.strip()]

    chunks: list[str] = []
    for part in raw_parts:
        if len(part) > max_size:
            chunks.extend(_split_at_sentence(part, max_size))
        else:
            chunks.append(part)

    return _merge_small_chunks(chunks, min_size)


# ---------------------------------------------------------------------------
# 판례 청킹: 섹션 헤더 기반 분할
# ---------------------------------------------------------------------------

_PRECEDENT_HEADERS = re.compile(
    r"(?=\[(판결요지|판시사항|참조조문|참조판례|판례내용|주\s*문|이\s*유|원심판결)\])"
)


def _chunk_precedent(text: str, max_size: int, min_size: int) -> list[str]:
    """판례를 [판결요지], [참조조문] 등 헤더 경계에서 분할한다."""
    raw_parts = _PRECEDENT_HEADERS.split(text)
    raw_parts = [p for p in raw_parts if p.strip()]

    chunks: list[str] = []
    for part in raw_parts:
        if len(part) > max_size:
            chunks.extend(_split_at_sentence(part, max_size))
        else:
            chunks.append(part)

    return _merge_small_chunks(chunks, min_size)


# ---------------------------------------------------------------------------
# 자문/보안 문서 청킹: 규칙 기반 문단 분할
# ---------------------------------------------------------------------------

# 빈 줄 2개 이상, 번호 패턴, 제목 패턴
_CONSULTATION_BOUNDARY = re.compile(
    r"(?:\n\s*\n\s*\n)"                    # 빈 줄 2개 이상
    r"|(?=\n\s*(?:\d+\.\s|[가-힣]\.\s))"   # 번호 패턴 (1. 가. 등)
    r"|(?=\n\s*[-•]\s)"                     # 불릿 포인트
)


def _chunk_consultation(text: str, max_size: int, min_size: int) -> list[str]:
    """자문/일반 문서를 문단 경계에서 분할한다."""
    raw_parts = _CONSULTATION_BOUNDARY.split(text)
    raw_parts = [p for p in raw_parts if p and p.strip()]

    if len(raw_parts) <= 1:
        # 경계를 못 찾으면 문장 경계로 분할
        return _split_at_sentence(text, max_size)

    chunks: list[str] = []
    for part in raw_parts:
        if len(part) > max_size:
            chunks.extend(_split_at_sentence(part, max_size))
        else:
            chunks.append(part)

    return _merge_small_chunks(chunks, min_size)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

_STRATEGY = {
    "law": _chunk_law,
    "precedent": _chunk_precedent,
    "consultation": _chunk_consultation,
}


def semantic_chunk_text(
    text: str,
    doc_type: str = "consultation",
    context_prefix: str = "",
    max_chunk_size: int = _DEFAULT_MAX_CHUNK,
    min_chunk_size: int = _DEFAULT_MIN_CHUNK,
) -> list[dict]:
    """문서 유형별 시맨틱 청킹을 수행한다.

    Args:
        text: 분할할 텍스트
        doc_type: 문서 유형 ("law", "precedent", "consultation")
        context_prefix: 각 청크 앞에 추가할 상위 문맥
        max_chunk_size: 최대 청크 크기 (문자 수)
        min_chunk_size: 최소 청크 크기 (미만 시 이전 청크에 병합)

    Returns:
        list[dict] — 각 원소는 {"text": str, "metadata": dict}
    """
    if not text or not text.strip():
        logger.warning("semantic_chunker_empty_text")
        return []

    chunk_fn = _STRATEGY.get(doc_type, _chunk_consultation)
    raw_chunks = chunk_fn(text, max_chunk_size, min_chunk_size)

    prefix = f"【{context_prefix}】\n" if context_prefix else ""

    results: list[dict] = []
    for i, chunk_text in enumerate(raw_chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue
        results.append({
            "text": prefix + chunk_text,
            "metadata": {
                "chunk_index": i,
                "chunk_type": doc_type,
            },
        })

    logger.info(
        "semantic_chunking_complete",
        doc_type=doc_type,
        total_chunks=len(results),
        text_length=len(text),
        has_context_prefix=bool(context_prefix),
    )

    return results
