"""답변 신뢰도 통합 — 검색 근거, AI 자체 평가, 인용 검증 결과를 하나로 합친다

화면에 신뢰도가 두 곳(검색 유사도 배지, AI가 쓴 '신뢰도' 섹션)에서 다르게 보이던 문제를 없애기 위해
세 신호 중 가장 보수적인(낮은) 값을 최종 신뢰도로 사용한다.
"""

from __future__ import annotations

import re

from models.chat import ConfidenceLevel

_ORDER = {ConfidenceLevel.LOW: 0, ConfidenceLevel.MEDIUM: 1, ConfidenceLevel.HIGH: 2}
_LABEL_TO_LEVEL = {"높음": ConfidenceLevel.HIGH, "보통": ConfidenceLevel.MEDIUM, "낮음": ConfidenceLevel.LOW}

# 답변 끝의 "### 신뢰도" 섹션 (다음 제목 또는 문서 끝까지)
_SECTION_RE = re.compile(r"(?m)^#{2,4}\s*신뢰도\s*$\n?([\s\S]*?)(?=^#{1,4}\s|\Z)")

_PROBLEM_STATUSES = {"not_found", "repealed"}
_UNCERTAIN_STATUSES = {"unknown_law", "unverified"}


def parse_stated_confidence(answer: str) -> tuple[ConfidenceLevel | None, str]:
    """AI 답변의 '신뢰도' 섹션에서 등급과 이유를 추출한다.

    Returns:
        (등급 또는 None, 이유 문장)
    """
    m = _SECTION_RE.search(answer or "")
    if not m:
        return None, ""
    body = m.group(1).strip()
    level_match = re.search(r"(높음|보통|낮음)", body)
    level = _LABEL_TO_LEVEL.get(level_match.group(1)) if level_match else None

    # 이유: 등급 표기 뒤의 문장 (마크다운 기호·구분자 제거)
    reason = body
    if level_match:
        reason = body[level_match.end():]
    reason = re.sub(r"[*_`]", "", reason)
    reason = re.sub(r"^[\s:：.\-—–,]+", "", reason)
    reason = re.sub(r"\s+", " ", reason).strip()
    # 등급 기준 설명 목록이 따라온 경우 첫 문장만
    reason = re.split(r"(?<=[.다요])\s", reason, maxsplit=1)[0] if reason else ""
    return level, reason[:200]


def combine_confidence(
    retrieval: ConfidenceLevel,
    stated: ConfidenceLevel | None,
    verified_citations: list[dict] | None,
) -> tuple[ConfidenceLevel, list[str]]:
    """세 신호 중 가장 낮은 신뢰도를 최종값으로 정한다.

    Returns:
        (최종 신뢰도, 하향 조정 사유 목록)
    """
    level = retrieval
    adjustments: list[str] = []

    if stated is not None and _ORDER[stated] < _ORDER[level]:
        level = stated
        adjustments.append("AI 자체 평가 반영")

    statuses = {c.get("status") for c in verified_citations or []}
    if statuses & _PROBLEM_STATUSES:
        if level != ConfidenceLevel.LOW:
            adjustments.append("확인되지 않는 조문 인용")
        level = ConfidenceLevel.LOW
    elif statuses & _UNCERTAIN_STATUSES and level == ConfidenceLevel.HIGH:
        level = ConfidenceLevel.MEDIUM
        adjustments.append("일부 인용 미확인")

    return level, adjustments
