"""조항 위치 찾기 — AI가 인용한 원문이 계약서 본문의 어디에 있는지 찾는다

AI가 인용한 원문은 띄어쓰기·줄바꿈·문장부호가 원문과 조금씩 다를 수 있으므로
공백을 무시한 비교 → 앞부분 일치 → 조항 번호(제N조) 순으로 찾는다.
화면에서 계약서 원문 위에 위험 조항을 강조하는 데 사용한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 앞부분 일치에 사용할 최소 글자 수 (공백 제외)
_PREFIX_LEN = 24
_MIN_QUOTE_LEN = 8

# 조항 제목: "제5조", "제 5 조", "제5조의2" (줄 시작 또는 문장 경계)
_ARTICLE_HEAD_RE = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    method: str  # exact / prefix / article


def _compact_with_map(text: str) -> tuple[str, list[int]]:
    """공백을 제거한 문자열과, 각 글자의 원문 위치 목록을 만든다."""
    chars: list[str] = []
    positions: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        chars.append(ch)
        positions.append(i)
    return "".join(chars), positions


def _strip_quote(quote: str) -> str:
    """인용 부호·말줄임표 등 원문에 없을 수 있는 장식을 제거한다."""
    q = (quote or "").strip()
    q = q.strip("\"'“”‘’「」『』")
    q = re.sub(r"(…|\.\.\.)\s*$", "", q)
    q = re.sub(r"^\s*(…|\.\.\.)", "", q)
    return q.strip()


def _article_key(text: str) -> str | None:
    m = _ARTICLE_HEAD_RE.search(text or "")
    if not m:
        return None
    return m.group(1) + (f"의{m.group(2)}" if m.group(2) else "")


def _locate_article(text: str, clause: str) -> Span | None:
    """'제5조(위약벌)' 같은 조항명으로 해당 조항 전체 범위를 찾는다."""
    key = _article_key(clause)
    if not key:
        return None
    heads = [
        (m.start(), m.group(1) + (f"의{m.group(2)}" if m.group(2) else ""))
        for m in _ARTICLE_HEAD_RE.finditer(text)
        # 본문 중 "제5조에 따라" 같은 참조가 아니라 조항 제목만: 줄 시작에 오는 경우
        if m.start() == 0 or text[m.start() - 1] == "\n"
    ]
    for idx, (pos, k) in enumerate(heads):
        if k == key:
            end = heads[idx + 1][0] if idx + 1 < len(heads) else len(text)
            while end > pos and text[end - 1].isspace():  # 조항 끝 공백 제외
                end -= 1
            return Span(pos, end, "article")
    return None


def locate_clause(text: str, quote: str | None, clause: str | None = None) -> Span | None:
    """계약서 본문에서 인용 원문의 위치를 찾는다. 못 찾으면 None."""
    if not text:
        return None
    compact_text, positions = _compact_with_map(text)

    q = _strip_quote(quote or "")
    compact_q, _ = _compact_with_map(q)
    if len(compact_q) >= _MIN_QUOTE_LEN:
        # 1) 공백 무시 전체 일치
        idx = compact_text.find(compact_q)
        if idx >= 0:
            return Span(positions[idx], positions[idx + len(compact_q) - 1] + 1, "exact")
        # 2) 앞부분 일치 → 원문 길이만큼 범위 추정
        prefix = compact_q[:_PREFIX_LEN]
        if len(prefix) >= _MIN_QUOTE_LEN:
            idx = compact_text.find(prefix)
            if idx >= 0:
                end_idx = min(idx + len(compact_q), len(compact_text)) - 1
                return Span(positions[idx], positions[end_idx] + 1, "prefix")

    # 3) 조항 번호로 조항 전체
    return _locate_article(text, clause or "") or _locate_article(text, q)
