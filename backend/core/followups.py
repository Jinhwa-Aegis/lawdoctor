"""후속 질문 추천 — 답변 직후 "이어서 물어볼까요" 질문 3개 생성

법률 지식이 없는 직원이 다음에 무엇을 물어야 할지 안내한다.
비용 절감을 위해 경량 모델(settings.query_rewrite_model, 기본 gpt-4o-mini)을 사용한다.
"""

from __future__ import annotations

import json
import re

import structlog

from config import settings
from core.llm import get_llm_client

logger = structlog.get_logger(__name__)

_MAX_QUESTIONS = 3
_MAX_QUESTION_LEN = 60
_ANSWER_CONTEXT_LIMIT = 2500  # 프롬프트에 넣을 답변 최대 길이(문자)

_FOLLOWUP_SYSTEM_PROMPT = """\
당신은 사내 {domain} 상담 서비스의 질문 추천 도우미입니다.
직원의 질문과 AI 답변을 보고, 직원이 이어서 물어보면 도움이 될 후속 질문 {n}개를 만드세요.

규칙:
- 답변에서 이미 충분히 설명한 내용은 다시 묻지 마십시오.
- 실무에서 바로 이어지는 질문(절차, 예외, 서류, 기한, 위반 시 제재 등)을 우선하십시오.
- 각 질문은 {max_len}자 이내의 자연스러운 한국어 의문문으로 쓰십시오.
- 반드시 JSON 배열만 출력하십시오. 예: ["질문1", "질문2", "질문3"]
"""


def parse_followups(raw: str) -> list[str]:
    """LLM 출력에서 질문 목록을 추출·정제한다. 형식이 깨져도 최대한 복구한다."""
    text = (raw or "").strip()
    # 코드 블록 제거
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)

    questions: list[str] = []
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("questions", [])
        if isinstance(data, list):
            questions = [str(q) for q in data]
    except (json.JSONDecodeError, TypeError):
        # 줄 단위 폴백: "1. 질문", "- 질문"
        for line in text.splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"')
            if line:
                questions.append(line)

    cleaned: list[str] = []
    seen: set[str] = set()
    for q in questions:
        q = q.strip().strip('"').strip()
        if not q or len(q) > _MAX_QUESTION_LEN * 2:
            continue
        if not q.endswith("?"):
            q = q.rstrip(".") + "?"
        if q in seen:
            continue
        seen.add(q)
        cleaned.append(q)
        if len(cleaned) >= _MAX_QUESTIONS:
            break
    return cleaned


async def generate_followups(question: str, answer: str, domain: str = "법률") -> list[str]:
    """질문과 답변을 바탕으로 후속 질문을 생성한다. 실패 시 빈 목록을 반환한다."""
    if not answer.strip():
        return []

    client = get_llm_client()
    try:
        raw = await client.generate(
            system_prompt=_FOLLOWUP_SYSTEM_PROMPT.format(
                domain=domain, n=_MAX_QUESTIONS, max_len=_MAX_QUESTION_LEN,
            ),
            messages=[{
                "role": "user",
                "content": f"직원 질문: {question}\n\nAI 답변:\n{answer[:_ANSWER_CONTEXT_LIMIT]}",
            }],
            max_tokens=300,
            model=settings.query_rewrite_model,
        )
        return parse_followups(raw)
    except Exception as exc:
        logger.warning("followup_generation_failed", error=str(exc))
        return []
