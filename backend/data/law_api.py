"""
국가법령정보센터 Open API 연동 모듈
"""

import httpx
import structlog
from typing import Optional
import xml.etree.ElementTree as ET

from config import settings
from core.embeddings import embed_batch
from core.hybrid_search import rebuild_bm25_index
from data.vector_store import get_vector_store
from data.ingest import chunk_text

logger = structlog.get_logger(__name__)

BASE_URL = "http://www.law.go.kr/DRF/lawSearch.do"
DETAIL_URL = "http://www.law.go.kr/DRF/lawService.do"

# 법령 검색 1회 최대 결과 수 (API 상한 100) — 결과가 가나다순이라 정확한 법령명을 찾으려면 넉넉히 받아야 함
SEARCH_DISPLAY_MAX = 100

# 저가치 조문 필터링 설정
_LOW_VALUE_PATTERNS = ["부칙", "경과규정"]
_MIN_ARTICLE_LENGTH = 30


def article_label(article_number: str) -> str:
    """조 번호를 표기 형식으로 변환한다. (예: 15 → 제15조, 25의2 → 제25조의2)"""
    main, _, branch = str(article_number).partition("의")
    return f"제{main}조" + (f"의{branch}" if branch else "")


def _collect_article_text(article: ET.Element) -> str:
    """조문단위 XML에서 조문내용 + 항·호·목 내용을 순서대로 합친 본문을 만든다.

    국가법령정보센터 응답은 조문 본문을 <항>/<호>/<목> 하위 요소에 담는다.
    <조문내용>만 읽으면 대부분의 조문이 제목 한 줄만 남는다.
    """
    lines: list[str] = []
    head = (article.findtext("조문내용", "") or "").strip()
    if head:
        lines.append(head)
    for hang in article.findall("항"):
        hang_text = (hang.findtext("항내용", "") or "").strip()
        if hang_text:
            lines.append(hang_text)
        for ho in hang.findall("호"):
            ho_text = (ho.findtext("호내용", "") or "").strip()
            if ho_text:
                lines.append(ho_text)
            for mok in ho.findall("목"):
                mok_text = (mok.findtext("목내용", "") or "").strip()
                if mok_text:
                    lines.append(mok_text)
    return "\n".join(lines)


def _filter_articles(articles: list[dict]) -> list[dict]:
    """부칙/경과규정 및 짧은 조문을 제외한다."""
    filtered = []
    for art in articles:
        title = art.get("article_title", "") or ""
        content = art.get("content", "") or ""
        # 부칙/경과규정 제외
        if any(pat in title for pat in _LOW_VALUE_PATTERNS):
            continue
        # 내용이 너무 짧은 조문 제외
        if len(content.strip()) < _MIN_ARTICLE_LENGTH:
            continue
        filtered.append(art)
    return filtered


async def search_laws(
    query: str,
    display: int = 20
) -> list[dict]:
    """
    법령 검색

    Args:
        query: 검색 쿼리 (법령명)
        display: 검색 결과 수

    Returns:
        법령 검색 결과 리스트
    """
    logger.info("searching_laws", query=query, display=display)

    params = {
        "OC": settings.law_api_key,
        "target": "law",
        "type": "XML",
        "query": query,
        "display": display,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()

        # HTML 에러 페이지 감지 (API 키 무효 등)
        content_str = response.content.decode("utf-8", errors="replace")
        if "<!DOCTYPE" in content_str or "<html" in content_str:
            logger.error(
                "law_api_returned_html",
                query=query,
                hint="API 키(LAW_API_KEY)가 유효하지 않거나 만료되었을 수 있습니다.",
            )
            raise ValueError(
                "국가법령정보센터 API가 HTML 에러 페이지를 반환했습니다. "
                "LAW_API_KEY가 유효한지 확인해주세요."
            )

        # XML 파싱
        root = ET.fromstring(response.content)

        results = []

        for law in root.findall(".//law"):
            law_id = law.findtext("법령ID", "")
            law_name = law.findtext("법령명한글", "")
            law_type = law.findtext("법령구분명", "")
            promulgation_date = law.findtext("공포일자", "")
            enforcement_date = law.findtext("시행일자", "")

            law_mst = law.findtext("법령일련번호", "")

            if law_id and law_name:
                results.append({
                    "law_id": law_id,
                    "law_mst": law_mst,
                    "law_name": law_name,
                    "law_type": law_type,
                    "promulgation_date": promulgation_date,
                    "enforcement_date": enforcement_date,
                })

        logger.info(
            "law_search_complete",
            query=query,
            result_count=len(results)
        )

        return results

    except httpx.HTTPError as e:
        logger.error(
            "law_search_http_error",
            query=query,
            error=str(e),
            exc_info=True
        )
        raise

    except ET.ParseError as e:
        logger.error(
            "law_search_xml_parse_error",
            query=query,
            error=str(e),
            exc_info=True
        )
        raise

    except Exception as e:
        logger.error(
            "law_search_failed",
            query=query,
            error=str(e),
            exc_info=True
        )
        raise


async def get_law_detail(law_mst: str) -> dict:
    """
    법령 상세 조문 가져오기

    Args:
        law_mst: 법령일련번호 (MST)

    Returns:
        법령 상세 정보 (조문 포함)
    """
    logger.info("fetching_law_detail", law_mst=law_mst)

    params = {
        "OC": settings.law_api_key,
        "target": "law",
        "MST": law_mst,
        "type": "XML",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(DETAIL_URL, params=params)
            response.raise_for_status()

        # HTML 에러 페이지 감지
        content_str = response.content.decode("utf-8", errors="replace")
        if "<!DOCTYPE" in content_str or "<html" in content_str:
            logger.error("law_api_returned_html", law_mst=law_mst)
            raise ValueError("국가법령정보센터 API가 HTML 에러 페이지를 반환했습니다. LAW_API_KEY를 확인해주세요.")

        # XML 파싱
        root = ET.fromstring(response.content)

        # lawService.do 응답: 최상위에 기본정보와 조문이 포함됨
        law_name = root.findtext(".//법령명_한글", "") or root.findtext(".//법령명한글", "")
        law_type = root.findtext(".//법령구분명", "") or root.findtext(".//법종구분", "")

        # 조문 추출
        articles = []
        for article in root.findall(".//조문단위"):
            article_num = article.findtext("조문번호", "")
            article_title = article.findtext("조문여백", "") or article.findtext("조문제목", "")
            # 조문내용은 "제15조(제목)" 한 줄뿐인 경우가 많고 본문은 항·호·목에 있으므로 합친다
            article_content = _collect_article_text(article)

            if article_content:
                articles.append({
                    "article_num": article_num,
                    "article_title": article_title,
                    "content": article_content,
                    # 가지 조문 번호 (예: 제15조의2 → "2"), 인용 검증에 사용
                    "article_branch": article.findtext("조문가지번호", "") or "",
                    # 장·절 제목 행 여부 (조문여부 = "전문")
                    "is_heading": article.findtext("조문여부", "") == "전문",
                })

        # 항(조문내 세부) 추출 — 조문단위가 없는 경우 대비
        if not articles:
            for article in root.findall(".//조문"):
                article_num = article.findtext("조문번호", "")
                article_title = article.findtext("조문제목", "")
                article_content = article.findtext("조문내용", "")
                if article_content:
                    articles.append({
                        "article_num": article_num,
                        "article_title": article_title,
                        "content": article_content,
                    })

        # 전체 조문 텍스트 결합
        full_text = "\n\n".join([
            f"제{art['article_num']}조 {art['article_title'] or ''}\n{art['content']}"
            for art in articles
        ])

        result = {
            "law_mst": law_mst,
            "law_name": law_name,
            "law_type": law_type,
            "articles": articles,
            "full_text": full_text,
            "article_count": len(articles),
        }

        logger.info(
            "law_detail_fetched",
            law_mst=law_mst,
            law_name=law_name,
            article_count=len(articles),
            text_length=len(full_text),
        )

        return result

    except httpx.HTTPError as e:
        logger.error(
            "law_detail_http_error",
            law_mst=law_mst,
            error=str(e),
            exc_info=True
        )
        raise

    except ET.ParseError as e:
        logger.error(
            "law_detail_xml_parse_error",
            law_mst=law_mst,
            error=str(e),
            exc_info=True
        )
        raise

    except Exception as e:
        logger.error(
            "law_detail_fetch_failed",
            law_mst=law_mst,
            error=str(e),
            exc_info=True
        )
        raise


async def fetch_and_ingest_laws(
    law_names: Optional[list[str]] = None
) -> dict[str, int]:
    """
    지정 법령을 검색하여 조문 추출 후 벡터 DB에 적재

    Args:
        law_names: 법령명 리스트 (기본값: 주요 6개 법령)

    Returns:
        법령별 적재된 청크 수 딕셔너리
    """
    if law_names is None:
        law_names = [
            "개인정보 보호법",
            "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
            "민법",
            "상법",
            "공동주택관리법",
            "주택법",
        ]

    logger.info(
        "fetching_and_ingesting_laws",
        law_count=len(law_names),
        law_names=law_names
    )

    results = {}
    vector_store = get_vector_store()

    for law_name in law_names:
        try:
            # 법령 검색
            logger.info("searching_law", law_name=law_name)
            # 검색 결과는 가나다순이라 짧은 법령명(예: "상법")은 정확히 일치하는 결과가 뒤쪽에 있다
            search_results = await search_laws(law_name, display=SEARCH_DISPLAY_MAX)

            if not search_results:
                logger.warning("no_search_results", law_name=law_name)
                results[law_name] = 0
                continue

            # 정확히 일치하는 법령만 적재 (다른 법령을 잘못 적재하지 않도록 첫 결과로 대체하지 않음)
            law_info = next(
                (sr for sr in search_results if sr["law_name"].replace(" ", "") == law_name.replace(" ", "")),
                None,
            )
            if law_info is None:
                logger.warning(
                    "no_exact_law_match",
                    law_name=law_name,
                    candidates=[sr["law_name"] for sr in search_results[:5]],
                )
                results[law_name] = 0
                continue

            law_id = law_info["law_id"]
            law_mst = law_info.get("law_mst", law_id)

            logger.info(
                "law_found",
                law_name=law_name,
                matched_name=law_info["law_name"],
                law_id=law_id,
                law_mst=law_mst,
            )

            # 법령 상세 조문 가져오기 (법령일련번호 사용)
            law_detail = await get_law_detail(law_mst)

            if not law_detail or not law_detail.get("articles"):
                logger.warning("no_law_content", law_name=law_name)
                results[law_name] = 0
                continue

            # 저가치 조문 필터링
            articles = _filter_articles(law_detail["articles"])
            if not articles:
                logger.warning("no_articles_after_filter", law_name=law_name)
                results[law_name] = 0
                continue

            # 조문별 청킹 (컨텍스트 프리픽스 포함)
            all_chunks = []
            global_chunk_idx = 0
            for art in articles:
                art_num = art.get("article_num", "")
                branch = str(art.get("article_branch", "") or "").strip()
                if branch and branch != "0":
                    art_num = f"{art_num}의{branch}"  # 가지 조문 (예: 제25조의2)
                art_title = art.get("article_title", "")
                content = art.get("content", "")
                if not content.strip():
                    continue

                context = f"{law_detail['law_name']} {article_label(art_num)}"
                if art_title:
                    context += f" ({art_title})"

                art_chunks = chunk_text(
                    content,
                    chunk_size=800,
                    overlap=150,
                    context_prefix=context,
                )

                for chunk in art_chunks:
                    chunk["metadata"].update({
                        "source": law_detail["law_name"],
                        "source_type": "law",
                        "law_id": law_id,
                        "law_type": law_detail.get("law_type", ""),
                        "article_number": art_num,
                        "article_title": art_title or "",
                    })
                    chunk["_global_index"] = global_chunk_idx
                    global_chunk_idx += 1

                all_chunks.extend(art_chunks)

            if not all_chunks:
                logger.warning("no_chunks_generated", law_name=law_name)
                results[law_name] = 0
                continue

            # 텍스트 추출
            texts = [chunk["text"] for chunk in all_chunks]

            # 임베딩 생성
            logger.info(
                "generating_law_embeddings",
                law_name=law_name,
                chunk_count=len(texts)
            )
            embeddings = await embed_batch(texts)

            # ChromaDB에 upsert + 잔여 청크 정리
            ids = [
                f"law_{law_mst}_chunk_{chunk['_global_index']}"
                for chunk in all_chunks
            ]

            metadatas = [chunk["metadata"] for chunk in all_chunks]

            vector_store.upsert_and_cleanup(
                collection_name="laws",
                id_prefix=f"law_{law_mst}_",
                documents=texts,
                metadatas=metadatas,
                ids=ids,
                embeddings=embeddings,
            )

            results[law_name] = len(all_chunks)

            logger.info(
                "law_ingested",
                law_name=law_name,
                chunks_ingested=len(all_chunks)
            )

        except Exception as e:
            logger.error(
                "law_ingestion_failed",
                law_name=law_name,
                error=str(e),
                exc_info=True
            )
            results[law_name] = 0

    total_chunks = sum(results.values())

    # BM25 인덱스 재빌드
    if total_chunks > 0:
        rebuild_bm25_index("laws")

    logger.info(
        "law_ingestion_complete",
        laws_processed=len(results),
        total_chunks=total_chunks,
        results=results
    )

    return results


# ---------------------------------------------------------------------------
# 판례 API
# ---------------------------------------------------------------------------

async def search_precedents(
    query: str,
    display: int = 20,
    page: int = 1,
) -> list[dict]:
    """
    판례 검색

    Args:
        query: 검색 키워드
        display: 검색 결과 수
        page: 페이지 번호

    Returns:
        판례 검색 결과 리스트
    """
    logger.info("searching_precedents", query=query, display=display, page=page)

    params = {
        "OC": settings.law_api_key,
        "target": "prec",
        "type": "XML",
        "query": query,
        "display": display,
        "page": page,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()

        # HTML 에러 페이지 감지
        content_str = response.content.decode("utf-8", errors="replace")
        if "<!DOCTYPE" in content_str or "<html" in content_str:
            logger.error("law_api_returned_html", query=query)
            raise ValueError("국가법령정보센터 API가 HTML 에러 페이지를 반환했습니다. LAW_API_KEY를 확인해주세요.")

        root = ET.fromstring(response.content)

        results = []
        for prec in root.findall(".//prec"):
            prec_id = prec.findtext("판례일련번호", "")
            case_name = prec.findtext("사건명", "")
            case_number = prec.findtext("사건번호", "")
            decision_date = prec.findtext("선고일자", "")
            court = prec.findtext("법원명", "")
            decision_type = prec.findtext("판결유형", "")

            if prec_id:
                results.append({
                    "prec_id": prec_id,
                    "case_name": case_name,
                    "case_number": case_number,
                    "decision_date": decision_date,
                    "court": court,
                    "decision_type": decision_type,
                })

        logger.info(
            "precedent_search_complete",
            query=query,
            result_count=len(results),
        )
        return results

    except httpx.HTTPError as e:
        logger.error("precedent_search_http_error", query=query, error=str(e), exc_info=True)
        raise
    except ET.ParseError as e:
        logger.error("precedent_search_xml_parse_error", query=query, error=str(e), exc_info=True)
        raise
    except Exception as e:
        logger.error("precedent_search_failed", query=query, error=str(e), exc_info=True)
        raise


async def get_precedent_detail(prec_id: str) -> dict:
    """
    판례 상세 조회

    Args:
        prec_id: 판례일련번호

    Returns:
        판례 상세 정보
    """
    logger.info("fetching_precedent_detail", prec_id=prec_id)

    params = {
        "OC": settings.law_api_key,
        "target": "prec",
        "type": "XML",
        "ID": prec_id,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(DETAIL_URL, params=params)
            response.raise_for_status()

        # HTML 에러 페이지 감지
        content_str = response.content.decode("utf-8", errors="replace")
        if "<!DOCTYPE" in content_str or "<html" in content_str:
            logger.error("law_api_returned_html", prec_id=prec_id)
            raise ValueError("국가법령정보센터 API가 HTML 에러 페이지를 반환했습니다. LAW_API_KEY를 확인해주세요.")

        root = ET.fromstring(response.content)

        case_name = root.findtext(".//사건명", "")
        case_number = root.findtext(".//사건번호", "")
        decision_date = root.findtext(".//선고일자", "")
        court = root.findtext(".//법원명", "")
        decision_type = root.findtext(".//판결유형", "")
        judgment_summary = root.findtext(".//판시사항", "")
        decision_summary = root.findtext(".//판결요지", "")
        reference_articles = root.findtext(".//참조조문", "")
        full_content = root.findtext(".//판례내용", "")

        # 주요 텍스트 조합
        text_parts = []
        if decision_summary:
            text_parts.append(f"[판결요지]\n{decision_summary}")
        if reference_articles:
            text_parts.append(f"[참조조문]\n{reference_articles}")
        if full_content:
            text_parts.append(f"[판례내용]\n{full_content}")
        elif judgment_summary:
            text_parts.append(f"[판시사항]\n{judgment_summary}")

        full_text = "\n\n".join(text_parts)

        result = {
            "prec_id": prec_id,
            "case_name": case_name,
            "case_number": case_number,
            "decision_date": decision_date,
            "court": court,
            "decision_type": decision_type,
            "judgment_summary": judgment_summary,
            "decision_summary": decision_summary,
            "reference_articles": reference_articles,
            "full_text": full_text,
        }

        logger.info(
            "precedent_detail_fetched",
            prec_id=prec_id,
            case_name=case_name,
            text_length=len(full_text),
        )
        return result

    except httpx.HTTPError as e:
        logger.error("precedent_detail_http_error", prec_id=prec_id, error=str(e), exc_info=True)
        raise
    except ET.ParseError as e:
        logger.error("precedent_detail_xml_parse_error", prec_id=prec_id, error=str(e), exc_info=True)
        raise
    except Exception as e:
        logger.error("precedent_detail_fetch_failed", prec_id=prec_id, error=str(e), exc_info=True)
        raise


async def fetch_and_ingest_precedents(
    keywords: Optional[list[str]] = None,
    max_per_keyword: int = 10,
) -> dict[str, int]:
    """
    키워드별 판례를 검색·상세 조회하여 벡터 DB에 적재

    Args:
        keywords: 검색 키워드 리스트 (기본: 주요 5개 키워드)
        max_per_keyword: 키워드당 최대 판례 수

    Returns:
        키워드별 적재된 청크 수 딕셔너리
    """
    if keywords is None:
        keywords = [
            "개인정보",
            "계약 해지",
            "하자담보",
            "공동주택 관리비",
            "정보통신망",
        ]

    logger.info(
        "fetching_and_ingesting_precedents",
        keyword_count=len(keywords),
        max_per_keyword=max_per_keyword,
    )

    results: dict[str, int] = {}
    vector_store = get_vector_store()

    for keyword in keywords:
        keyword_chunk_count = 0
        try:
            search_results = await search_precedents(keyword, display=max_per_keyword)

            if not search_results:
                logger.warning("no_precedent_results", keyword=keyword)
                results[keyword] = 0
                continue

            for prec_info in search_results:
                prec_id = prec_info["prec_id"]
                try:
                    detail = await get_precedent_detail(prec_id)

                    if not detail or not detail.get("full_text"):
                        continue

                    # 컨텍스트 프리픽스 포함 청킹
                    case_name = detail.get("case_name", "")
                    case_number = detail.get("case_number", "")
                    context = f"{case_name} ({case_number})" if case_number else case_name

                    from core.semantic_chunker import semantic_chunk_text
                    chunks = semantic_chunk_text(
                        detail["full_text"],
                        doc_type="precedent",
                        context_prefix=context,
                        max_chunk_size=800,
                    )
                    if not chunks:
                        continue

                    # 메타데이터 추가
                    for chunk in chunks:
                        chunk["metadata"].update({
                            "source": detail.get("case_name", ""),
                            "source_type": "precedent",
                            "case_name": detail.get("case_name", ""),
                            "case_number": detail.get("case_number", ""),
                            "court": detail.get("court", ""),
                            "decision_date": detail.get("decision_date", ""),
                            "decision_type": detail.get("decision_type", ""),
                        })

                    texts = [c["text"] for c in chunks]
                    embeddings = await embed_batch(texts)

                    ids = [
                        f"prec_{prec_id}_chunk_{c['metadata']['chunk_index']}"
                        for c in chunks
                    ]
                    metadatas = [c["metadata"] for c in chunks]

                    # ChromaDB에 upsert + 잔여 청크 정리
                    vector_store.upsert_and_cleanup(
                        collection_name="precedents",
                        id_prefix=f"prec_{prec_id}_",
                        documents=texts,
                        metadatas=metadatas,
                        ids=ids,
                        embeddings=embeddings,
                    )

                    keyword_chunk_count += len(chunks)

                    logger.info(
                        "precedent_ingested",
                        prec_id=prec_id,
                        case_name=detail.get("case_name", ""),
                        chunks=len(chunks),
                    )

                except Exception as e:
                    logger.error(
                        "precedent_detail_ingestion_failed",
                        prec_id=prec_id,
                        error=str(e),
                        exc_info=True,
                    )

            results[keyword] = keyword_chunk_count

        except Exception as e:
            logger.error(
                "precedent_keyword_ingestion_failed",
                keyword=keyword,
                error=str(e),
                exc_info=True,
            )
            results[keyword] = 0

    total_chunks = sum(results.values())

    # BM25 인덱스 재빌드
    if total_chunks > 0:
        rebuild_bm25_index("precedents")

    logger.info(
        "precedent_ingestion_complete",
        keywords_processed=len(results),
        total_chunks=total_chunks,
        results=results,
    )

    return results
