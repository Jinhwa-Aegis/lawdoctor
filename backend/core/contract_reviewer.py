"""계약서 리뷰 모듈 — 파일 업로드 → 텍스트 추출 → 리스크 분석"""

import asyncio
import json
import os
import re
from typing import Optional

import fitz  # PyMuPDF
import structlog
from pydantic import BaseModel, ValidationError, field_validator

from config import settings
from core.citation_verifier import verify_citations
from core.clause_locator import locate_clause
from core.contract_checklists import (
    AUTO_DETECT,
    CONTRACT_TYPES,
    detect_contract_type,
    format_checklist_prompt,
    get_checklist,
)
from core.llm import get_llm_client, SYSTEM_PROMPT_CONTRACT_REVIEW
from data.ingest import extract_text_from_hwp

logger = structlog.get_logger()


# === 리스크 분석 결과 스키마 ===

class _LenientModel(BaseModel):
    """LLM 출력 관용 처리: 문자열 필드의 null은 빈 문자열로 바꾼다."""

    @field_validator("*", mode="before")
    @classmethod
    def _none_to_empty_str(cls, v, info):
        field = cls.model_fields.get(info.field_name)
        if v is None and field is not None and field.annotation is str:
            return ""
        return v


class RiskItem(_LenientModel):
    clause: str               # 해당 조항/내용
    risk_level: str           # high / medium / low
    description: str          # 리스크 설명
    legal_basis: str = ""     # 근거 법령
    suggestion: Optional[str] = None       # 수정 제안 (협상 포인트)
    risk_score: Optional[int] = None       # 위험 점수 0~100
    original_text: Optional[str] = None    # 계약서 원문
    revised_text: Optional[str] = None     # 수정 조문안
    # 계약서 원문(contract_text) 안에서의 위치 — 화면 강조용 (못 찾으면 None)
    span_start: Optional[int] = None
    span_end: Optional[int] = None

    @field_validator("risk_score", mode="before")
    @classmethod
    def _coerce_score(cls, v):
        """점수가 숫자가 아니면 버리고(None), 0~100 범위로 자른다."""
        try:
            return max(0, min(100, int(float(v))))
        except (TypeError, ValueError):
            return None


class MissingClause(_LenientModel):
    clause_name: str          # 누락 조항명
    importance: str           # high / medium / low
    description: str          # 필요 사유
    suggested_text: Optional[str] = None  # 추가할 조문 예시


class ChecklistResult(_LenientModel):
    item_id: str              # 점검 항목 ID
    name: str = ""            # 점검 항목명 (서버에서 채움)
    status: str               # ok / risk / missing / na
    comment: str = ""         # 판단 근거
    clause_ref: str = ""      # 관련 조항
    legal_basis: str = ""     # 점검표 기준 근거 법령 (서버에서 채움)
    auto_adjusted: bool = False  # 판정이 근거와 모순되어 서버가 보정했는지


class ContractReviewResult(BaseModel):
    contract_type: str                   # 계약서 유형 (NDA, 위탁계약 등)
    summary: str                         # 계약서 요약
    risk_items: list[RiskItem]           # 리스크 포인트
    missing_clauses: list[MissingClause] # 누락 조항
    overall_risk: str                    # 전체 위험도 (high/medium/low)
    recommendation: str                  # 종합 의견
    our_position: str = ""               # 이지스엔터프라이즈의 계약상 지위
    checklist_type: str = "general"      # 적용된 점검표 유형 키
    checklist_label: str = ""            # 적용된 점검표 이름
    checklist_auto_detected: bool = False  # 유형 자동 감지 여부
    checklist_results: list[ChecklistResult] = []
    verified_citations: list[dict] = []  # 근거 법령 인용 검증 결과
    contract_text: str = ""              # 분석한 계약서 원문 (화면 표시용)
    file_name: str = ""                  # 업로드 파일명


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

async def review_contract(filepath: str, contract_type: str = AUTO_DETECT) -> ContractReviewResult:
    """계약서 파일을 분석하여 리스크 리포트 생성

    Args:
        filepath: 업로드된 계약서 경로
        contract_type: 점검표 유형 키 (auto면 경량 모델로 자동 감지)
    """
    logger.info("계약서 리뷰 시작", filepath=filepath, contract_type=contract_type)

    # 1. 텍스트 추출 (blocking I/O를 별도 스레드에서 실행)
    text = await asyncio.to_thread(extract_text, filepath)
    if not text.strip():
        raise ValueError("파일에서 텍스트를 추출할 수 없습니다. 스캔 PDF는 지원하지 않습니다.")

    # 텍스트 길이 제한 (너무 긴 계약서 처리)
    max_chars = 50000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n... (이하 생략, 문서가 너무 길어 일부만 분석합니다)"

    # 2. 점검표 유형 결정
    auto_detected = contract_type == AUTO_DETECT or contract_type not in CONTRACT_TYPES
    type_key = await detect_contract_type(text) if auto_detected else contract_type

    # 3. LLM으로 리스크 분석 (유형별 점검표 주입)
    client = get_llm_client()
    messages = [
        {
            "role": "user",
            "content": (
                f"{format_checklist_prompt(type_key)}\n\n"
                f"다음 계약서를 분석해주세요.\n\n---\n{text}\n---"
            ),
        }
    ]

    response = await client.generate(
        system_prompt=SYSTEM_PROMPT_CONTRACT_REVIEW,
        messages=messages,
        max_tokens=8192,
    )

    # 4. JSON 파싱 + 점검표 정규화
    result = _parse_review_response(response)
    result.contract_text = text
    attach_clause_spans(result)
    result.checklist_type = type_key
    result.checklist_label = CONTRACT_TYPES[type_key].label
    result.checklist_auto_detected = auto_detected
    result.checklist_results = normalize_checklist_results(type_key, result.checklist_results)

    # 5. 근거 법령 인용 검증
    basis_text = "\n".join(item.legal_basis for item in result.risk_items if item.legal_basis)
    if basis_text:
        try:
            result.verified_citations = await verify_citations(basis_text)
        except Exception as exc:
            logger.warning("계약서 근거 법령 검증 실패", error=str(exc))

    logger.info(
        "계약서 리뷰 완료",
        contract_type=result.contract_type,
        checklist_type=type_key,
        risk_count=len(result.risk_items),
        checklist_missing=sum(c.status == "missing" for c in result.checklist_results),
        overall_risk=result.overall_risk,
    )

    return result


def attach_clause_spans(result: "ContractReviewResult") -> None:
    """각 위험 항목이 계약서 원문의 어디에 있는지 찾아 기록한다."""
    for item in result.risk_items:
        span = locate_clause(result.contract_text, item.original_text, item.clause)
        if span:
            item.span_start, item.span_end = span.start, span.end


_VALID_CHECK_STATUSES = {"ok", "risk", "missing", "na"}

# '충족(ok)' 판정인데 근거에 불리함을 뜻하는 표현이 있으면 모순 — "불리하지 않음" 같은 부정형은 제외
_NEGATIVE_COMMENT_RE = re.compile(
    r"(불리|불명확|과도|과중|일방적|일방에게만)(?!\s*하지\s*않|\s*지\s*않|하지않|지않)"
)


def _contradicts_ok(comment: str) -> bool:
    """'충족' 판정과 모순되는 근거인지 판단한다."""
    return bool(_NEGATIVE_COMMENT_RE.search(comment or ""))


def normalize_checklist_results(type_key: str, raw: list[ChecklistResult]) -> list[ChecklistResult]:
    """점검표 순서대로 결과를 정렬하고, AI가 빠뜨린 항목은 미판정(na)으로 채운다.

    점검표에 없는 item_id는 버린다.
    """
    by_id = {r.item_id: r for r in raw}
    normalized: list[ChecklistResult] = []
    for item in get_checklist(type_key):
        r = by_id.get(item.id)
        if r is None:
            r = ChecklistResult(
                item_id=item.id, status="na",
                comment="AI가 판정하지 않은 항목입니다. 직접 확인하십시오.",
            )
        status = r.status if r.status in _VALID_CHECK_STATUSES else "na"
        adjusted = False
        if status == "ok" and _contradicts_ok(r.comment):
            status, adjusted = "risk", True
        normalized.append(r.model_copy(update={
            "name": item.name, "legal_basis": item.legal_basis, "status": status,
            "auto_adjusted": adjusted,
        }))
    return normalized


def _parse_items(model: type[BaseModel], raw) -> list:
    """항목 목록을 하나씩 검증한다. 잘못된 항목 하나 때문에 전체가 버려지지 않게 건너뛴다."""
    items = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        try:
            items.append(model(**entry))
        except ValidationError as exc:
            logger.warning("리뷰 항목 파싱 건너뜀", model=model.__name__, error=str(exc))
    return items


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
        if not isinstance(data, dict):
            raise ValueError("JSON 객체가 아닙니다")
        return ContractReviewResult(
            contract_type=data.get("contract_type") or "기타",
            summary=data.get("summary") or "",
            risk_items=_parse_items(RiskItem, data.get("risk_items")),
            missing_clauses=_parse_items(MissingClause, data.get("missing_clauses")),
            overall_risk=data.get("overall_risk") or "medium",
            recommendation=data.get("recommendation") or "",
            our_position=data.get("our_position") or "",
            checklist_results=[
                r for r in _parse_items(ChecklistResult, data.get("checklist_results")) if r.item_id
            ],
        )
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        logger.warning("LLM 응답 파싱 실패", error=str(e))
        return ContractReviewResult(
            contract_type="분류 불가",
            summary="계약서 분석 중 오류가 발생했습니다. 다시 시도해주세요.",
            risk_items=[],
            missing_clauses=[],
            overall_risk="medium",
            recommendation="AI가 계약서를 정상적으로 분석하지 못했습니다. 외부 전문가 자문을 권장합니다.",
        )
