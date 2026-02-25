"""
문서 수집 및 벡터 DB 적재 모듈

PDF, DOCX, HWP 파일에서 텍스트를 추출하여 벡터 DB에 적재한다.
"""

import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib

import fitz  # PyMuPDF
import structlog
from docx import Document as DocxDocument
from pathlib import Path
from typing import Optional

try:
    import olefile
except ImportError:
    olefile = None

from core.embeddings import embed_batch
from data.vector_store import get_vector_store

logger = structlog.get_logger(__name__)

# 지원하는 문서 확장자
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".hwp", ".hwpx"}


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    context_prefix: str = "",
) -> list[dict]:
    """
    텍스트를 청크로 분할

    Args:
        text: 분할할 텍스트
        chunk_size: 청크 크기 (문자 단위)
        overlap: 청크 간 중복 크기
        context_prefix: 각 청크 앞에 추가할 상위 문맥 (예: 법령명, 조항명)

    Returns:
        청크 리스트, 각 청크는 {"text": str, "metadata": dict} 형식
    """
    if not text or not text.strip():
        logger.warning("empty_text_provided")
        return []

    chunks = []
    start = 0
    text_length = len(text)
    chunk_index = 0

    # context_prefix가 있으면 청크 본문 앞에 접두사를 붙인다
    prefix = f"【{context_prefix}】\n" if context_prefix else ""

    while start < text_length:
        end = start + chunk_size
        raw_chunk = text[start:end]

        # 공백 텍스트 스킵
        if raw_chunk.strip():
            chunks.append({
                "text": prefix + raw_chunk.strip(),
                "metadata": {
                    "chunk_index": chunk_index,
                    "start_pos": start,
                    "end_pos": min(end, text_length),
                }
            })
            chunk_index += 1

        start += chunk_size - overlap

    logger.info(
        "text_chunked",
        total_chunks=len(chunks),
        text_length=text_length,
        chunk_size=chunk_size,
        overlap=overlap,
        has_context_prefix=bool(context_prefix),
    )

    return chunks


def extract_text_from_pdf(filepath: str) -> str:
    """
    PyMuPDF로 PDF 텍스트 추출

    Args:
        filepath: PDF 파일 경로

    Returns:
        추출된 전체 텍스트
    """
    logger.info("extracting_pdf_text", filepath=filepath)

    try:
        doc = fitz.open(filepath)
        text_parts = []

        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(page_text)

        page_count = len(doc)
        doc.close()

        full_text = "\n\n".join(text_parts)

        logger.info(
            "pdf_text_extracted",
            filepath=filepath,
            pages=page_count,
            text_length=len(full_text)
        )

        return full_text

    except Exception as e:
        logger.error(
            "pdf_extraction_failed",
            filepath=filepath,
            error=str(e),
            exc_info=True
        )
        raise


def extract_text_from_docx(filepath: str) -> str:
    """
    python-docx로 DOCX 텍스트 추출

    Args:
        filepath: DOCX 파일 경로

    Returns:
        추출된 전체 텍스트
    """
    logger.info("extracting_docx_text", filepath=filepath)

    try:
        doc = DocxDocument(filepath)
        text_parts = []

        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)

        # 테이블 내 텍스트도 추출
        for table in doc.tables:
            for row in table.rows:
                row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_texts:
                    text_parts.append(" | ".join(row_texts))

        full_text = "\n\n".join(text_parts)

        logger.info(
            "docx_text_extracted",
            filepath=filepath,
            paragraphs=len(doc.paragraphs),
            text_length=len(full_text),
        )
        return full_text

    except Exception as e:
        logger.error(
            "docx_extraction_failed",
            filepath=filepath,
            error=str(e),
            exc_info=True,
        )
        raise


def _decode_hwp_text(data: bytes) -> str:
    """HWP 바이너리 레코드에서 UTF-16LE 텍스트 디코딩"""
    result = []
    i = 0

    # 확장 제어 문자 — 16바이트(문자 자체 2바이트 + 인라인 데이터 14바이트)를 차지
    extended_controls = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}

    while i < len(data) - 1:
        char_code = struct.unpack_from("<H", data, i)[0]

        if char_code == 0:
            break
        elif char_code == 13:  # 문단 구분
            result.append("\n")
            i += 2
        elif char_code in extended_controls:
            # 확장 제어 문자: 총 16바이트 건너뜀
            i += 16
        elif char_code < 32:
            # 기타 인라인 제어 문자
            i += 2
        else:
            result.append(chr(char_code))
            i += 2

    return "".join(result)


def _parse_hwp_section(data: bytes) -> str:
    """HWP 섹션 바이너리 데이터에서 텍스트 레코드 파싱"""
    text_parts = []
    i = 0
    # HWPTAG_PARA_TEXT 태그 ID
    PARA_TEXT_TAG = 67

    while i < len(data) - 4:
        # 레코드 헤더: 4바이트
        # [0:9] Tag ID, [10:19] Level, [20:31] Size
        header = struct.unpack_from("<I", data, i)[0]
        tag_id = header & 0x3FF
        size = (header >> 20) & 0xFFF

        if size == 0xFFF:
            # 확장 크기: 다음 4바이트
            if i + 8 > len(data):
                break
            size = struct.unpack_from("<I", data, i + 4)[0]
            i += 8
        else:
            i += 4

        if i + size > len(data):
            break

        if tag_id == PARA_TEXT_TAG and size > 0:
            text = _decode_hwp_text(data[i : i + size])
            if text.strip():
                text_parts.append(text.strip())

        i += size

    return "\n".join(text_parts)


def _extract_text_from_hwpx(filepath: str) -> str:
    """
    HWPX(ZIP/XML 기반) 파일에서 텍스트 추출

    HWPX는 ZIP 아카이브 내 XML 파일(Contents/section*.xml)에 텍스트가 저장된다.
    """
    logger.info("extracting_hwpx_text", filepath=filepath)

    text_parts = []

    with zipfile.ZipFile(filepath, "r") as zf:
        # section XML 파일 찾기
        section_files = sorted(
            [n for n in zf.namelist() if n.startswith("Contents/section") and n.endswith(".xml")]
        )

        if not section_files:
            # 대체 경로 탐색
            section_files = sorted(
                [n for n in zf.namelist() if "section" in n.lower() and n.endswith(".xml")]
            )

        for section_file in section_files:
            xml_data = zf.read(section_file)
            try:
                root = ET.fromstring(xml_data)
            except ET.ParseError:
                logger.warning("hwpx_xml_parse_failed", file=section_file)
                continue

            # 텍스트 태그에서 추출 (대소문자 무관)
            text_tags = {"t", "char", "text"}
            para_tags = {"p", "para", "paragraph"}
            for elem in root.iter():
                tag_local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                tag_lower = tag_local.lower()
                if tag_lower in text_tags and elem.text:
                    text_parts.append(elem.text)
                elif tag_lower in para_tags:
                    has_text_child = any(
                        (child.tag.split("}")[-1] if "}" in child.tag else child.tag).lower()
                        in text_tags
                        for child in elem
                    )
                    if not has_text_child and text_parts and text_parts[-1] != "\n":
                        text_parts.append("\n")

    # 연속된 텍스트를 문단 단위로 결합
    full_text = ""
    for part in text_parts:
        if part == "\n":
            full_text += "\n\n"
        else:
            full_text += part

    logger.info(
        "hwpx_text_extracted",
        filepath=filepath,
        sections=len(section_files),
        text_length=len(full_text),
    )
    return full_text


def _extract_text_from_hwpml(filepath: str) -> str:
    """
    HWPML(순수 XML) 형식의 HWP 파일에서 텍스트 추출

    HWPML은 ZIP으로 감싸지 않은 순수 XML 파일이며, .hwp 확장자를 가진다.
    파일이 <?xml 로 시작하는 것이 특징이다.

    다양한 HWPML 버전의 태그 구조를 지원:
    - OWPML(2011+): <hp:t>, <hp:p>, <hp:run> 등
    - HWPML 2.x: <TEXT>, <CHAR>, <P> 등
    - 기타 XML-HWP 변형
    """
    logger.info("extracting_hwpml_text", filepath=filepath)

    # 텍스트를 포함하는 태그 이름 (대소문자 무관)
    TEXT_TAGS = {"t", "char", "text"}
    # 문단 구분 태그 이름 (대소문자 무관)
    PARA_TAGS = {"p", "para", "paragraph"}
    # 텍스트 추출에서 제외할 메타데이터 태그 (대소문자 무관)
    EXCLUDE_TAGS = {
        "style", "script", "meta", "head", "header",
        "bindata", "charshape", "parashape", "borderfill",
        "facename", "substfont", "typeinfo", "beginnum",
        "autonum", "autospacing", "linebreak", "fieldbegin",
        "fieldend", "bookmark", "comment", "dutmal",
        "charpr", "parapr", "linesegarray", "lineseg",
        "tabpr", "colpr", "footnoteshape", "pageshape",
        "fnpr", "tcpr", "celladdr", "cellspan", "cellsz",
        "shapeobject", "formobject", "eqedit", "img",
    }

    text_parts = []

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()

        # 1차: 알려진 텍스트 태그에서 추출
        for elem in root.iter():
            tag_local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            tag_lower = tag_local.lower()

            if tag_lower in TEXT_TAGS and elem.text:
                text_parts.append(elem.text)
            elif tag_lower in PARA_TAGS:
                # 자식 중 텍스트 태그가 없는 빈 문단 → 줄바꿈
                has_text_child = any(
                    (child.tag.split("}")[-1] if "}" in child.tag else child.tag).lower()
                    in TEXT_TAGS
                    for child in elem
                )
                if not has_text_child and text_parts and text_parts[-1] != "\n":
                    text_parts.append("\n")

        # 2차: 텍스트 태그로 내용을 못 찾으면, 모든 텍스트 노드에서 추출 시도
        has_content = any(p != "\n" for p in text_parts)
        if not has_content:
            logger.info("hwpml_fallback_to_all_text", filepath=filepath)
            text_parts = []
            for elem in root.iter():
                tag_local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                tag_lower = tag_local.lower()

                if tag_lower in EXCLUDE_TAGS:
                    continue

                if elem.text and elem.text.strip():
                    text_parts.append(elem.text.strip())
                if elem.tail and elem.tail.strip():
                    text_parts.append(elem.tail.strip())

    except ET.ParseError as e:
        logger.error("hwpml_xml_parse_failed", filepath=filepath, error=str(e))
        raise ValueError(f"HWPML XML 파싱 실패: {e}")

    # 연속된 텍스트를 문단 단위로 결합
    full_text = ""
    for part in text_parts:
        if part == "\n":
            full_text += "\n\n"
        else:
            full_text += part

    logger.info(
        "hwpml_text_extracted",
        filepath=filepath,
        text_length=len(full_text),
    )
    return full_text


def _extract_text_from_hwp5(filepath: str) -> str:
    """
    HWP5(OLE2 기반) 파일에서 텍스트 추출
    """
    if olefile is None:
        raise ImportError(
            "HWP 파일 처리를 위해 olefile 패키지가 필요합니다. "
            "pip install olefile 을 실행하세요."
        )

    ole = olefile.OleFileIO(filepath)

    # FileHeader에서 압축 여부 확인
    header_data = ole.openstream("FileHeader").read()
    is_compressed = bool(header_data[36] & 1)

    text_parts = []
    section_idx = 0

    while True:
        section_name = f"BodyText/Section{section_idx}"
        if not ole.exists(section_name):
            break

        data = ole.openstream(section_name).read()

        # zlib 압축 해제
        if is_compressed:
            try:
                data = zlib.decompress(data, -15)
            except zlib.error:
                logger.warning(
                    "hwp_decompress_failed",
                    section=section_name,
                )

        section_text = _parse_hwp_section(data)
        if section_text.strip():
            text_parts.append(section_text)

        section_idx += 1

    ole.close()

    full_text = "\n\n".join(text_parts)

    logger.info(
        "hwp5_text_extracted",
        filepath=filepath,
        sections=section_idx,
        text_length=len(full_text),
    )
    return full_text


def extract_text_from_hwp(filepath: str) -> str:
    """
    HWP/HWPX 파일에서 텍스트 추출

    HWPML(순수 XML), HWPX(ZIP/XML), HWP5(OLE2) 순서로 형식을 판별하여 시도한다.

    Args:
        filepath: HWP 파일 경로

    Returns:
        추출된 전체 텍스트
    """
    logger.info("extracting_hwp_text", filepath=filepath)

    # 파일 매직 바이트로 형식 판별
    with open(filepath, "rb") as f:
        magic = f.read(4)

    logger.info("hwp_file_magic", magic=magic.hex(), filepath=filepath)

    # 1) HWPML(순수 XML) 형식 — <?xml 시그니처
    if magic[:4] == b"<?xm":
        try:
            text = _extract_text_from_hwpml(filepath)
            if text.strip():
                return text
            logger.warning(
                "hwpml_parsed_but_empty",
                filepath=filepath,
                msg="XML 파싱 성공했으나 텍스트가 비어있음",
            )
        except Exception as e:
            logger.warning(
                "hwpml_extraction_failed",
                filepath=filepath,
                error=str(e),
            )
        # XML 파일이면 OLE2 시도는 의미 없으므로 여기서 에러 반환
        raise ValueError(
            f"HWPML(XML) 형식의 HWP 파일에서 텍스트를 추출할 수 없습니다. "
            f"파일이 비어있거나 지원하지 않는 XML 구조입니다. "
            f"파일 시그니처: {magic.hex()}"
        )

    # 2) HWPX(ZIP) 형식 시도 — PK 시그니처 또는 is_zipfile
    if magic[:2] == b"PK" or zipfile.is_zipfile(filepath):
        try:
            text = _extract_text_from_hwpx(filepath)
            if text.strip():
                return text
            logger.warning(
                "hwpx_parsed_but_empty",
                filepath=filepath,
                msg="HWPX ZIP 파싱 성공했으나 텍스트가 비어있음",
            )
        except Exception as e:
            logger.warning(
                "hwpx_extraction_failed_fallback_to_hwp5",
                filepath=filepath,
                error=str(e),
            )

    # 3) HWP5(OLE2) 형식 시도
    try:
        text = _extract_text_from_hwp5(filepath)
        if text.strip():
            return text
        raise ValueError("HWP5 파일에서 텍스트를 추출할 수 없습니다 (빈 내용).")
    except Exception as e:
        logger.error(
            "hwp_all_extraction_failed",
            filepath=filepath,
            magic=magic.hex(),
            error=str(e),
            exc_info=True,
        )
        raise ValueError(
            f"HWP 파일을 읽을 수 없습니다. "
            f"지원 형식: HWP5(OLE2), HWPX(ZIP/XML), HWPML(XML). "
            f"파일 시그니처: {magic.hex()}"
        )


def extract_text(filepath: str) -> str:
    """
    파일 확장자에 따라 적절한 텍스트 추출 함수를 호출

    Args:
        filepath: 문서 파일 경로 (.pdf, .docx, .hwp)

    Returns:
        추출된 전체 텍스트
    """
    ext = Path(filepath).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext == ".docx":
        return extract_text_from_docx(filepath)
    elif ext in (".hwp", ".hwpx"):
        return extract_text_from_hwp(filepath)
    else:
        raise ValueError(
            f"지원하지 않는 파일 형식입니다: {ext}. "
            f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}"
        )


async def ingest_pdf(
    filepath: str,
    source_type: str = "consultation"
) -> int:
    """
    문서 파일(PDF, DOCX, HWP)을 파싱하고 임베딩 생성 후 ChromaDB에 적재

    Args:
        filepath: 문서 파일 경로 (.pdf, .docx, .hwp)
        source_type: 문서 출처 타입 (consultation, law, etc.)

    Returns:
        적재된 청크 수
    """
    logger.info(
        "ingesting_document",
        filepath=filepath,
        source_type=source_type
    )

    try:
        # 텍스트 추출 (확장자에 따라 자동 분기)
        text = extract_text(filepath)

        if not text.strip():
            logger.warning("empty_pdf_content", filepath=filepath)
            return 0

        # 텍스트 청킹
        chunks = chunk_text(text)

        if not chunks:
            logger.warning("no_chunks_generated", filepath=filepath)
            return 0

        # 메타데이터 추가
        file_path = Path(filepath)
        for chunk in chunks:
            chunk["metadata"].update({
                "source": file_path.name,
                "source_type": source_type,
                "filepath": str(file_path.absolute()),
            })

        # 텍스트만 추출
        texts = [chunk["text"] for chunk in chunks]

        # 임베딩 생성
        logger.info("generating_embeddings", chunk_count=len(texts))
        embeddings = await embed_batch(texts)

        # ChromaDB에 저장
        vector_store = get_vector_store()

        # ID 생성 (파일명 + 청크 인덱스)
        ids = [
            f"{file_path.stem}_chunk_{chunk['metadata']['chunk_index']}"
            for chunk in chunks
        ]

        # 메타데이터만 추출
        metadatas = [chunk["metadata"] for chunk in chunks]

        # 컬렉션 이름 결정
        collection_name = "consultations" if source_type == "consultation" else "laws"

        vector_store.add_documents(
            collection_name=collection_name,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

        logger.info(
            "pdf_ingestion_complete",
            filepath=filepath,
            chunks_ingested=len(chunks)
        )

        return len(chunks)

    except Exception as e:
        logger.error(
            "pdf_ingestion_failed",
            filepath=filepath,
            error=str(e),
            exc_info=True
        )
        raise


async def ingest_directory(
    dir_path: str,
    source_type: str = "consultation"
) -> dict[str, int]:
    """
    디렉토리 내 모든 PDF 파일 처리

    Args:
        dir_path: 디렉토리 경로
        source_type: 문서 출처 타입

    Returns:
        파일별 적재된 청크 수 딕셔너리
    """
    logger.info(
        "ingesting_directory",
        dir_path=dir_path,
        source_type=source_type
    )

    directory = Path(dir_path)

    if not directory.exists():
        logger.error("directory_not_found", dir_path=dir_path)
        raise FileNotFoundError(f"Directory not found: {dir_path}")

    if not directory.is_dir():
        logger.error("path_not_directory", dir_path=dir_path)
        raise ValueError(f"Path is not a directory: {dir_path}")

    # PDF 파일 찾기
    pdf_files = list(directory.glob("**/*.pdf"))

    logger.info("pdf_files_found", count=len(pdf_files))

    results = {}
    total_chunks = 0

    for pdf_file in pdf_files:
        try:
            chunk_count = await ingest_pdf(
                str(pdf_file),
                source_type=source_type
            )
            results[pdf_file.name] = chunk_count
            total_chunks += chunk_count

        except Exception as e:
            logger.error(
                "file_ingestion_failed",
                filepath=str(pdf_file),
                error=str(e)
            )
            results[pdf_file.name] = 0

    logger.info(
        "directory_ingestion_complete",
        dir_path=dir_path,
        files_processed=len(results),
        total_chunks=total_chunks
    )

    return results
