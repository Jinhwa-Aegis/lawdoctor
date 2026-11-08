"""질문 다듬기 — 직원의 짧거나 모호한 질문을 답변하기 좋은 법률 질문으로 정리

입력창의 "다듬기" 버튼에서 사용한다. 사용자가 말하지 않은 사실을 지어내지 않고,
빠진 정보는 [대괄호] 자리표시자로 남겨 사용자가 채우게 한다.
경량 모델(settings.query_rewrite_model)을 사용한다.
"""

from __future__ import annotations

import structlog

from config import settings
from core.llm import get_llm_client

logger = structlog.get_logger(__name__)

_MAX_INPUT_CHARS = 2000

_REFINE_SYSTEM_PROMPT = """\
당신은 사내 법률 상담 서비스의 질문 정리 도우미입니다.
직원이 쓴 질문을 법률 AI가 정확히 답할 수 있도록 다듬으십시오.

규칙:
- 원래 질문의 의도와 사실관계를 그대로 유지하고, 직원이 말하지 않은 사실은 절대 추가하지 마십시오.
- 답변에 꼭 필요한데 빠진 정보(당사자의 지위, 계약 유형, 시점, 금액 등)는 [대괄호]로 자리만 표시하십시오.
  예: "[당사가 위탁자인지 수탁자인지]"
- 무엇을 알고 싶은지(가능 여부, 절차, 위험, 필요한 서류 등)가 드러나는 의문문으로 끝내십시오.
- 3문장 이내, 존댓말로 작성하십시오.
- 다듬은 질문만 출력하고 설명·따옴표·머리말은 쓰지 마십시오.
"""


async def refine_question(question: str) -> str:
    """질문을 다듬어 반환한다. 실패하면 원문을 그대로 반환한다."""
    text = (question or "").strip()
    if not text:
        return text
    try:
        refined = await get_llm_client().generate(
            system_prompt=_REFINE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text[:_MAX_INPUT_CHARS]}],
            max_tokens=400,
            model=settings.query_rewrite_model,
        )
        refined = refined.strip().strip('"').strip()
        return refined or text
    except Exception as exc:
        logger.warning("질문 다듬기 실패", error=str(exc))
        return text
