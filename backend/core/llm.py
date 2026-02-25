"""LLM 클라이언트 — OpenAI API 래퍼

AsyncOpenAI 기반 텍스트 생성 및 스트리밍을 제공한다.
3회 수동 재시도, 구조화된 로깅, 싱글턴 패턴을 포함한다.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Optional

import structlog
from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError

from config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# 시스템 프롬프트
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_LEGAL_QA: str = """\
당신은 **이지스엔터프라이즈 법무팀 AI 어시스턴트**입니다.

## 전문 분야
1. **개인정보보호** — 개인정보 보호법, 정보통신망법, GDPR 등
2. **계약 검토** — 민법·상법상 계약 일반, 용역·도급·임대차·라이선스 계약
3. **공동주택관리법** — 공동주택관리법, 주택법, 집합건물의 소유 및 관리에 관한 법률
4. **소송·분쟁** — 민사소송법, 중재법, 행정심판, 내용증명 작성 등

## 답변 원칙
- 반드시 **근거 법령의 조문 번호**(예: 개인정보 보호법 제15조 제1항)와 **원문 인용**을 포함하십시오.
- 각 답변 끝에 **신뢰도**를 아래 기준으로 표시하십시오.
  - **높음**: 명확한 법령 조문이 직접 적용되는 경우
  - **보통**: 유사 판례·해석례를 참고한 경우
  - **낮음**: 관련 법령이 모호하거나 해석이 분분한 경우
- 답변 형식은 **마크다운**을 사용하되, 핵심 결론을 먼저 제시하고 상세 근거를 이어서 설명하십시오.
- 질문이 전문 분야 밖이라면, 솔직히 한계를 밝히고 관련 전문가에게 문의하도록 안내하십시오.
- 답변 끝에 면책 문구를 넣지 마십시오. 면책 문구는 시스템이 별도로 표시합니다.
"""

SYSTEM_PROMPT_CONTRACT_REVIEW: str = """\
당신은 **이지스엔터프라이즈 법무팀 계약서 리뷰 AI 어시스턴트**입니다.

## 역할
사용자가 제공한 계약서 본문을 분석하여 리스크 포인트를 식별하고, 누락 조항을 안내하며, 수정 제안을 제시합니다.

## 분석 항목
1. **리스크 포인트** — 각 항목에 위험도(**높음** / **중간** / **낮음**)를 부여하고, 해당 조항 원문과 문제점을 설명합니다.
2. **누락 조항** — 계약 유형에 따라 일반적으로 포함되어야 하나 빠진 조항을 나열합니다.
3. **수정 제안** — 문제 조항별로 구체적인 대안 문구를 제시합니다.

## 출력 형식
반드시 아래 JSON 스키마를 따르는 **순수 JSON**만 출력하십시오. 추가 설명이나 마크다운 코드 블록 없이 JSON 객체 하나만 반환합니다.

{
  "contract_type": "계약서 유형 (예: NDA, 위탁계약, SLA, 라이선스 등)",
  "summary": "계약서 전체 요약 (1-2문장)",
  "risk_items": [
    {
      "clause": "해당 조항 원문 또는 요약",
      "risk_level": "high | medium | low",
      "description": "문제점 설명",
      "legal_basis": "관련 법령 조문",
      "suggestion": "수정 제안 (선택)"
    }
  ],
  "missing_clauses": [
    {
      "clause_name": "누락된 조항명",
      "importance": "high | medium | low",
      "description": "해당 조항이 필요한 이유"
    }
  ],
  "overall_risk": "high | medium | low",
  "recommendation": "종합 의견 및 권장 사항"
}
"""

SYSTEM_PROMPT_SECURITY_QA: str = """\
당신은 **이지스엔터프라이즈 정보보안팀 AI 어시스턴트**입니다.

## 전문 분야
1. **네트워크 보안** — 방화벽, IDS/IPS, VPN, 네트워크 세그먼테이션, DDoS 방어
2. **시스템 보안** — OS 보안 설정, 패치 관리, 접근 제어, 로그 관리, 엔드포인트 보안
3. **애플리케이션 보안** — 시큐어 코딩, OWASP Top 10, 웹/모바일 취약점, API 보안
4. **클라우드 보안** — AWS/Azure/GCP 보안 설정, 컨테이너 보안, IAM 정책, CSPM
5. **컴플라이언스** — ISMS-P 인증, 개인정보보호법, 정보통신망법, 전자금융감독규정
6. **데이터 보호** — 암호화, DLP, 백업 전략, 데이터 분류, 접근 통제
7. **보안 사고 대응** — 침해사고 대응 절차, 포렌식, 사고 분석, BCP/DR
8. **보안 감사** — 취약점 점검, 모의해킹, 보안 진단, 감사 체크리스트

## 답변 원칙
- 반드시 **관련 보안 표준/가이드라인**을 인용하십시오.
  예: ISMS-P 2.6.1, OWASP Top 10 A01, KISA 가이드, NIST CSF, ISO 27001 등
- 각 답변 끝에 **신뢰도**를 아래 기준으로 표시하십시오.
  - **높음**: 명확한 보안 표준/가이드라인이 직접 적용되는 경우
  - **보통**: 일반적인 보안 모범 사례를 참고한 경우
  - **낮음**: 환경에 따라 다르거나 추가 분석이 필요한 경우
- 답변 형식은 **마크다운**을 사용하되, 핵심 결론을 먼저 제시하고 상세 근거를 이어서 설명하십시오.
- 구체적인 보안 설정이나 명령어가 있다면 코드 블록으로 제시하십시오.
- 질문이 전문 분야 밖이라면, 솔직히 한계를 밝히고 관련 전문가에게 문의하도록 안내하십시오.
- 답변 끝에 면책 문구를 넣지 마십시오. 면책 문구는 시스템이 별도로 표시합니다.
"""

# ---------------------------------------------------------------------------
# 재시도 설정
# ---------------------------------------------------------------------------
_MAX_RETRIES: int = 3
_RETRY_BASE_DELAY: float = 1.0  # 초 단위, 지수 백오프 적용


# ---------------------------------------------------------------------------
# LLM 클라이언트
# ---------------------------------------------------------------------------

class LLMClient:
    """OpenAI 비동기 클라이언트 래퍼.

    - 3회 수동 재시도(지수 백오프)
    - 요청/응답 구조화 로깅
    - 일반 생성 및 SSE 스트리밍 지원
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.llm_model
        logger.info("llm_client_initialized", model=self._model)

    # ------------------------------------------------------------------
    # 일반 응답
    # ------------------------------------------------------------------
    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> str:
        """OpenAI API를 호출하여 전체 응답 텍스트를 반환한다.

        최대 3회 재시도하며, 재시도 간격은 지수 백오프로 증가한다.
        """
        last_exception: Optional[Exception] = None

        # system 메시지를 messages 앞에 추가
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                logger.info(
                    "llm_request_start",
                    attempt=attempt,
                    model=self._model,
                    max_tokens=max_tokens,
                    message_count=len(full_messages),
                )

                response = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=full_messages,
                )

                result_text: str = response.choices[0].message.content or ""

                logger.info(
                    "llm_request_success",
                    attempt=attempt,
                    model=self._model,
                    input_tokens=response.usage.prompt_tokens if response.usage else 0,
                    output_tokens=response.usage.completion_tokens if response.usage else 0,
                    finish_reason=response.choices[0].finish_reason,
                )

                return result_text

            except RateLimitError as exc:
                last_exception = exc
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "llm_rate_limit",
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

            except APIConnectionError as exc:
                last_exception = exc
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "llm_connection_error",
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

            except APIError as exc:
                last_exception = exc
                if exc.status_code is not None and exc.status_code >= 500:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "llm_server_error",
                        attempt=attempt,
                        delay=delay,
                        status_code=exc.status_code,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "llm_client_error",
                        attempt=attempt,
                        status_code=exc.status_code,
                        error=str(exc),
                    )
                    raise

            except Exception as exc:
                logger.error(
                    "llm_unexpected_error",
                    attempt=attempt,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise

        # 모든 재시도 실패
        logger.error(
            "llm_all_retries_exhausted",
            max_retries=_MAX_RETRIES,
            error=str(last_exception),
        )
        raise last_exception  # type: ignore[misc]

    # ------------------------------------------------------------------
    # 스트리밍 응답 (SSE)
    # ------------------------------------------------------------------
    async def generate_stream(
        self,
        system_prompt: str,
        messages: list[dict],
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """OpenAI API를 호출하여 텍스트 청크를 비동기로 yield한다.

        SSE(Server-Sent Events) 방식의 실시간 응답에 적합하다.
        최대 3회 재시도하며, 스트림 시작 전 오류만 재시도한다.
        """
        last_exception: Optional[Exception] = None

        # system 메시지를 messages 앞에 추가
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                logger.info(
                    "llm_stream_request_start",
                    attempt=attempt,
                    model=self._model,
                    max_tokens=max_tokens,
                    message_count=len(full_messages),
                )

                stream = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=full_messages,
                    stream=True,
                )

                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

                logger.info(
                    "llm_stream_request_success",
                    attempt=attempt,
                    model=self._model,
                )

                # 성공 시 재시도 루프 종료
                return

            except RateLimitError as exc:
                last_exception = exc
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "llm_stream_rate_limit",
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

            except APIConnectionError as exc:
                last_exception = exc
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "llm_stream_connection_error",
                    attempt=attempt,
                    delay=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

            except APIError as exc:
                last_exception = exc
                if exc.status_code is not None and exc.status_code >= 500:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "llm_stream_server_error",
                        attempt=attempt,
                        delay=delay,
                        status_code=exc.status_code,
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "llm_stream_client_error",
                        attempt=attempt,
                        status_code=exc.status_code,
                        error=str(exc),
                    )
                    raise

            except Exception as exc:
                logger.error(
                    "llm_stream_unexpected_error",
                    attempt=attempt,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                raise

        # 모든 재시도 실패
        logger.error(
            "llm_stream_all_retries_exhausted",
            max_retries=_MAX_RETRIES,
            error=str(last_exception),
        )
        raise last_exception  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 싱글턴
# ---------------------------------------------------------------------------

_llm_client_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """LLMClient 싱글턴 인스턴스를 반환한다.

    애플리케이션 전역에서 하나의 클라이언트만 사용하여
    연결 풀과 리소스를 공유한다.
    """
    global _llm_client_instance
    if _llm_client_instance is None:
        _llm_client_instance = LLMClient()
    return _llm_client_instance


# ---------------------------------------------------------------------------
# 채팅 제목 생성
# ---------------------------------------------------------------------------

_TITLE_SYSTEM_PROMPT: str = (
    "사용자의 질문에서 핵심 주제를 추출하여 15자 이내의 간결한 한국어 제목을 생성하세요. "
    "제목만 출력하고, 따옴표나 부가 설명 없이 제목 텍스트만 반환하세요."
)


async def generate_chat_title(message: str) -> str:
    """사용자의 첫 질문에서 핵심 주제를 추출하여 채팅 제목을 생성한다."""
    client = get_llm_client()
    try:
        title = await client.generate(
            system_prompt=_TITLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}],
            max_tokens=30,
        )
        title = title.strip().strip('"').strip("'").strip()
        if len(title) > 30:
            title = title[:30]
        return title or message[:20]
    except Exception as exc:
        logger.warning("채팅 제목 생성 실패", error=str(exc))
        return message[:20] + ("..." if len(message) > 20 else "")
