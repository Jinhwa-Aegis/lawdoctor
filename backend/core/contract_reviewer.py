"""계약서 리뷰 모듈 — 파일 업로드 → 텍스트 추출 → 리스크 분석"""

import asyncio
import json
import os
import re
from typing import Optional

import fitz  # PyMuPDF
import structlog
from pydantic import BaseModel, ValidationError

from config import settings
from core.llm import get_llm_client, SYSTEM_PROMPT_CONTRACT_REVIEW
from data.ingest import extract_text_from_hwp

logger = structlog.get_logger()


# === 리스크 분석 결과 스키마 ===

class RiskItem(BaseModel):
    clause: str               # 해당 조항/내용
    risk_level: str           # high / medium / low
    description: str          # 리스크 설명
    legal_basis: str          # 근거 법령
    suggestion: Optional[str] = None  # 수정 제안


class MissingClause(BaseModel):
    clause_name: str          # 누락 조항명
    importance: str           # high / medium / low
    description: str          # 필요 사유


class ContractReviewResult(BaseModel):
    contract_type: str                   # 계약서 유형 (NDA, 위탁계약 등)
    summary: str                         # 계약서 요약
    risk_items: list[RiskItem]           # 리스크 포인트
    missing_clauses: list[MissingClause] # 누락 조항
    overall_risk: str                    # 전체 위험도 (high/medium/low)
    recommendation: str                  # 종합 의견


# === 텍스트 추출 ===

def extract_text_from_pdf(filepath: str) -> str:
    """PDF에서 텍스트 추출"""
    doc = fitz.open(filepath)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts)


def extract_text_from_docx(filepath: str) -> str:
    """DOCX에서 텍스트 추출"""
    from docx import Document
    doc = Document(filepath)
    return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])


def extract_text(filepath: str) -> str:
    """파일 확장자에 따라 텍스트 추출"""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext == ".docx":
        return extract_text_from_docx(filepath)
    elif ext in (".hwp", ".hwpx"):
        return extract_text_from_hwp(filepath)
    elif ext == ".txt":
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")


# === 계약서 리뷰 ===

async def review_contract(filepath: str) -> ContractReviewResult:
    """계약서 파일을 분석하여 리스크 리포트 생성"""
    logger.info("계약서 리뷰 시작", filepath=filepath)

    # 1. 텍스트 추출 (blocking I/O를 별도 스레드에서 실행)
    text = await asyncio.to_thread(extract_text, filepath)
    if not text.strip():
        raise ValueError("파일에서 텍스트를 추출할 수 없습니다. 스캔 PDF는 지원하지 않습니다.")

    # 텍스트 길이 제한 (너무 긴 계약서 처리)
    max_chars = 50000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n... (이하 생략, 문서가 너무 길어 일부만 분석합니다)"

    # 2. LLM으로 리스크 분석
    client = get_llm_client()
    messages = [
        {
            "role": "user",
            "content": f"다음 계약서를 분석해주세요.\n\n---\n{text}\n---",
        }
    ]

    response = await client.generate(
        system_prompt=SYSTEM_PROMPT_CONTRACT_REVIEW,
        messages=messages,
        max_tokens=8192,
    )

    # 3. JSON 파싱
    result = _parse_review_response(response)
    logger.info(
        "계약서 리뷰 완료",
        contract_type=result.contract_type,
        risk_count=len(result.risk_items),
        overall_risk=result.overall_risk,
    )

    return result


def _parse_review_response(response: str) -> ContractReviewResult:
    """LLM 응답에서 JSON을 파싱하여 리뷰 결과 생성"""
    # JSON 블록 추출 시도
    match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
    if match:
        json_str = match.group(1).strip()
    else:
        json_str = response.strip()

    try:
        data = json.loads(json_str)
        return ContractReviewResult(
            contract_type=data.get("contract_type", "기타"),
            summary=data.get("summary", ""),
            risk_items=[RiskItem(**item) for item in data.get("risk_items", [])],
            missing_clauses=[MissingClause(**item) for item in data.get("missing_clauses", [])],
            overall_risk=data.get("overall_risk", "medium"),
            recommendation=data.get("recommendation", ""),
        )
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("LLM 응답 파싱 실패", error=str(e))
        return ContractReviewResult(
            contract_type="분류 불가",
            summary="계약서 분석 중 오류가 발생했습니다. 다시 시도해주세요.",
            risk_items=[],
            missing_clauses=[],
            overall_risk="medium",
            recommendation="AI가 계약서를 정상적으로 분석하지 못했습니다. 외부 전문가 자문을 권장합니다.",
        )
