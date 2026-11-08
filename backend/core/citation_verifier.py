"""인용 검증 — AI 답변에 인용된 법령 조문의 실존 여부 확인

답변 본문에서 「법령명 제N조(의M)」 패턴을 추출하고,
국가법령정보센터 Open API(현행 법령)로 해당 조문이 실제로 존재하는지 검증한다.
API 호출이 불가능하면 로컬 벡터 DB(laws 컬렉션)로 대체 확인한다.

검증 상태:
- verified    : 현행 법령에 해당 조문이 존재함
- repealed    : 조문 번호는 있으나 삭제된 조문 (예: "제22조 삭제 <2020. 2. 4.>")
- not_found   : 법령은 확인되었으나 해당 조문이 존재하지 않음 (할루시네이션 의심)
- unknown_law : 법령명을 확인할 수 없음
- unverified  : 검증 수행 불가 (API 오류 등)
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, asdict

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

STATUS_VERIFIED = "verified"
STATUS_REPEALED = "repealed"
STATUS_NOT_FOUND = "not_found"
STATUS_UNKNOWN_LAW = "unknown_law"
STATUS_UNVERIFIED = "unverified"

_MAX_CITATIONS = 15            # 답변당 최대 검증 건수
_CACHE_TTL_SECONDS = 24 * 3600  # 법령 조문 인덱스 캐시 유효기간
_CONCURRENCY = 4               # 동시 API 호출 수

# 약칭 → 정식 법령명
LAW_ALIASES: dict[str, str] = {
    "개인정보보호법": "개인정보 보호법",
    "정보통신망법": "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "전자상거래법": "전자상거래 등에서의 소비자보호에 관한 법률",
    "집합건물법": "집합건물의 소유 및 관리에 관한 법률",
    "상가임대차법": "상가건물 임대차보호법",
    "상가임대차보호법": "상가건물 임대차보호법",
    "주택임대차법": "주택임대차보호법",
    "전자문서법": "전자문서 및 전자거래 기본법",
    "하도급법": "하도급거래 공정화에 관한 법률",
    "약관법": "약관의 규제에 관한 법률",
    "약관규제법": "약관의 규제에 관한 법률",
    "공정거래법": "독점규제 및 공정거래에 관한 법률",
    "위치정보법": "위치정보의 보호 및 이용 등에 관한 법률",
    "신용정보법": "신용정보의 이용 및 보호에 관한 법률",
    "전자서명법": "전자서명법",
}

# 자주 인용되는 정식 법령명 (공백 제거 형태로 비교)
_KNOWN_LAWS: list[str] = [
    "개인정보 보호법",
    "정보통신망 이용촉진 및 정보보호 등에 관한 법률",
    "민법",
    "상법",
    "공동주택관리법",
    "주택법",
    "근로기준법",
    "민사소송법",
    "민사집행법",
    "형법",
    "중재법",
    "행정심판법",
    "전자서명법",
    "저작권법",
    "특허법",
    "부가가치세법",
    "법인세법",
    "소득세법",
    "주택임대차보호법",
    *LAW_ALIASES.values(),
]

# 삭제된 조문 본문 패턴: "제22조 삭제 <2020. 2. 4.>"
_REPEALED_RE = re.compile(r"^\s*제\s*\d+\s*조(?:\s*의\s*\d+)?\s*(?:\([^)]*\))?\s*삭제")

# 「같은 법」류 지시어
_SAME_LAW_TOKENS = {"같은법", "동법", "이법", "위법"}

# 법령명 바로 앞에 붙어 법령명으로 오인되는 토큰(조사로 끝나는 단어 등)
_PARTICLE_SUFFIXES = (
    "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "로", "으로",
    "에서", "따라", "따르면", "의하면", "근거", "및", "또는", "등",
)

# 법령이 아닌 일반 명사 — 인용으로 보지 않는다 (예: "관련 법령 제15조", "회사 취업규칙 제10조")
_NON_LAW_NAMES = {
    "법령", "관련법령", "해당법령", "법", "법률", "관련법", "해당법", "관련법률", "해당법률",
    "규칙", "취업규칙", "내부규칙", "사내규칙", "운영규칙", "시행령", "시행규칙", "명령",
}

# 실제 법령명은 이 단어로 끝나지 않는다 — 마지막 토큰이 이것이면 인용이 아님
# ("법", "법률"은 "~에 관한 법률"처럼 정식 법령명 끝에 오므로 제외)
_NON_LAW_LAST_TOKENS = {
    "법령", "관련법령", "해당법령", "취업규칙", "내부규칙", "사내규칙", "운영규칙", "명령",
}

# 미등록 법령명 후보로 시도할 최대 토큰 수 (긴 정식 법령명 고려)
_MAX_NAME_TOKENS = 7

# 법령명 후보 + 조문 번호
# 예: "개인정보 보호법 제15조", "같은 법 시행령 제3조의2", "민법 제 750 조"
_CITATION_RE = re.compile(
    r"((?:[가-힣A-Za-z·ㆍ]+\s?){1,12}?(?:법률|법|령|규칙))"  # 법령명 후보
    r"[\"'「」『』“”‘’)\]]*"                                   # 닫는 따옴표·괄호 (예: 「개인정보 보호법」)
    r"\s*제\s*(\d+)\s*조"                                     # 조 번호
    r"(?:\s*의\s*(\d+))?"                                     # 가지 번호
)

# 같은 법령의 연속 인용: "민법 제393조, 제398조", "제15조 제1항 및 제17조"
_CONTINUATION_RE = re.compile(
    r"(?:\s*제\s*\d+\s*[항호])*"                 # 앞 인용의 항·호 생략 허용
    r"\s*(?:,|및|ㆍ|·|와|과|또는)\s*"             # 연결어
    r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?"
)

# 마크다운 강조 기호 (예: **개인정보 보호법** 제15조)
_MARKDOWN_EMPHASIS_RE = re.compile(r"[*_`]+")


# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------

@dataclass
class CitationCheck:
    """인용 1건의 검증 결과"""

    raw: str                 # 답변 본문에 나온 원문 표현
    law_name: str            # 정식 법령명 (해석 실패 시 원문 후보)
    article: str             # 조 번호 (예: "15", "15의2")
    status: str              # verified / repealed / not_found / unknown_law / unverified
    article_title: str = ""  # 조문 제목 (검증 성공 시)
    excerpt: str = ""        # 조문 원문 발췌 (검증 성공 시)
    source: str = ""         # 검증 출처 (law_api / local)
    law_url: str = ""        # 국가법령정보센터 조문 링크

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 법령명 정규화
# ---------------------------------------------------------------------------

def _compact(name: str) -> str:
    """공백·가운뎃점 제거한 비교용 문자열"""
    return re.sub(r"[\s·ㆍ]", "", name)


_KNOWN_BY_COMPACT: dict[str, str] = {_compact(n): n for n in _KNOWN_LAWS}
_ALIAS_BY_COMPACT: dict[str, str] = {_compact(k): v for k, v in LAW_ALIASES.items()}


def _lookup_known(name: str) -> str | None:
    """약칭/정식명 사전에서 정식 법령명을 찾는다. 시행령·시행규칙은 본법 기준으로 해석."""
    compact = _compact(name)
    for suffix in ("시행령", "시행규칙"):
        if compact.endswith(suffix) and len(compact) > len(suffix):
            base = _lookup_known(compact[: -len(suffix)])
            return f"{base} {suffix}" if base else None
    return _ALIAS_BY_COMPACT.get(compact) or _KNOWN_BY_COMPACT.get(compact)


def name_candidates(candidate: str) -> list[str]:
    """사전에 없는 법령명 후보를 긴 것부터 짧은 순으로 만든다.

    정규식은 법령명 앞의 단어까지 함께 잡을 수 있으므로(예: "지급해야 하며 근로자퇴직급여 보장법"),
    뒤쪽 토큰 묶음을 후보로 만들어 API에서 정확히 일치하는 것을 찾는다.
    조사로 끝나는 토큰으로 시작하는 후보와 일반 명사(법령, 취업규칙 등)는 제외한다.
    """
    tokens = candidate.split()[-_MAX_NAME_TOKENS:]
    if not tokens or _compact(tokens[-1]) in _NON_LAW_LAST_TOKENS:
        return []
    result: list[str] = []
    for i in range(len(tokens)):
        sub = tokens[i:]
        if i < len(tokens) - 1 and sub[0].endswith(_PARTICLE_SUFFIXES):
            continue
        name = " ".join(sub)
        if _compact(name) in _NON_LAW_NAMES:
            continue
        result.append(name)
    return result


def resolve_law_name(candidate: str) -> tuple[str, bool]:
    """정규식 후보 문자열에서 법령명을 해석한다.

    앞쪽 토큰을 하나씩 떼어내며 사전에 있는 법령명을 찾는다.
    사전에 없으면 가장 짧은 후보(마지막 토큰 쪽)를 표시용 이름으로 반환한다.

    Returns:
        (법령명, 사전 확인 여부) — 법령으로 볼 수 없으면 ("", False)
    """
    tokens = candidate.split()
    for i in range(len(tokens)):
        found = _lookup_known(" ".join(tokens[i:]))
        if found:
            return found, True

    candidates = name_candidates(candidate)
    if not candidates:
        return "", False
    # 표시용: 두 토큰 이상인 가장 짧은 후보 (예: "근로자퇴직급여 보장법"), 없으면 마지막 후보
    multi = [c for c in candidates if len(c.split()) >= 2]
    return (multi[-1] if multi else candidates[-1]), False


# ---------------------------------------------------------------------------
# 인용 추출
# ---------------------------------------------------------------------------

def _article_key(num: str, branch: str | None) -> str:
    return num + (f"의{branch}" if branch else "")


def extract_law_citations(text: str) -> list[dict]:
    """답변 본문에서 법령 조문 인용을 추출한다 (중복 제거, 등장 순서 유지).

    - "같은 법", "동법", "같은 법 시행령" 등 지시어는 직전에 인용된 법령으로 해석한다.
    - "민법 제393조, 제398조"처럼 법령명 없이 이어지는 조문도 같은 법령으로 추출한다.

    Returns:
        [{"raw", "law_name", "article", "known", "candidates"}, ...]
        candidates: 사전에 없는 법령일 때 API로 시도할 법령명 후보 (긴 것부터)
    """
    text = _MARKDOWN_EMPHASIS_RE.sub("", text or "")
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()
    last: dict | None = None  # 직전 인용의 법령 정보 {"law_name", "known", "candidates"}

    def _add(raw: str, law: dict, article: str) -> bool:
        key = (_compact(law["law_name"]), article)
        if key in seen:
            return True
        seen.add(key)
        results.append({"raw": raw, "article": article, **law})
        return len(results) < _MAX_CITATIONS

    for m in _CITATION_RE.finditer(text):
        candidate = m.group(1).strip()
        article = _article_key(m.group(2), m.group(3))

        tokens = candidate.split()
        compact_last = _compact(tokens[-1]) if tokens else ""
        compact_tail2 = _compact("".join(tokens[-2:]))
        compact_tail3 = _compact("".join(tokens[-3:]))

        # 지시어 처리
        if compact_tail3.endswith(("같은법시행령", "동법시행령", "같은법시행규칙", "동법시행규칙")):
            if not last:
                continue
            suffix = "시행규칙" if compact_tail3.endswith("시행규칙") else "시행령"
            base = last["law_name"].split(" 시행")[0]
            law = {"law_name": f"{base} {suffix}", "known": last["known"],
                   "candidates": [f"{base} {suffix}"]}
        elif compact_last in _SAME_LAW_TOKENS or compact_tail2 in _SAME_LAW_TOKENS:
            if not last:
                continue
            law = dict(last)
        else:
            law_name, known = resolve_law_name(candidate)
            if not law_name:
                continue  # 일반 명사 (관련 법령, 취업규칙 등)
            law = {
                "law_name": law_name,
                "known": known,
                "candidates": [law_name] if known else name_candidates(candidate),
            }

        last = law
        if not _add(m.group(0).strip(), law, article):
            break

        # 연속 인용 처리: ", 제398조", "및 제17조"
        pos = m.end()
        while True:
            cont = _CONTINUATION_RE.match(text, pos)
            if not cont:
                break
            if not _add(cont.group(0).strip(), law, _article_key(cont.group(1), cont.group(2))):
                return results
            pos = cont.end()

    return results


# ---------------------------------------------------------------------------
# 법령 조문 인덱스 (국가법령정보센터) — 프로세스 내 캐시
# ---------------------------------------------------------------------------

_FETCH_TIMEOUT_SECONDS = 8.0  # 법령 1건 조회 대기 한도 (다운로드 자체는 백그라운드에서 계속)

# compact 법령명 → (만료시각, 정식명, {조번호: (제목, 내용)} 또는 None)
_law_index_cache: dict[str, tuple[float, str, dict[str, tuple[str, str]] | None]] = {}
_inflight: dict[str, asyncio.Future] = {}
_cache_lock = asyncio.Lock()


async def _fetch_law_index(law_name: str) -> tuple[str, dict[str, tuple[str, str]] | None]:
    """국가법령정보센터에서 법령을 찾아 조문 인덱스를 반환한다.

    Returns:
        (정식 법령명, {조번호: (조문제목, 조문내용)}) — 법령을 찾지 못하면 인덱스는 None

    Raises:
        API 호출 실패 시 예외 전파 (호출부에서 unverified 처리)
    """
    from data.law_api import SEARCH_DISPLAY_MAX, search_laws, get_law_detail

    target = _compact(law_name)
    # 결과가 가나다순이라 "상법"처럼 짧은 이름은 정확히 일치하는 결과가 뒤쪽에 있다
    search_results = await search_laws(law_name, display=SEARCH_DISPLAY_MAX)

    # 정확히 일치하는 법령만 인정 (유사 법령 오매칭 방지)
    match = next(
        (r for r in search_results if _compact(r.get("law_name", "")) == target),
        None,
    )
    if match is None:
        return law_name, None

    detail = await get_law_detail(match.get("law_mst") or match["law_id"])
    index: dict[str, tuple[str, str]] = {}
    for art in detail.get("articles", []):
        num = str(art.get("article_num", "")).strip()
        if not num:
            continue
        branch = str(art.get("article_branch", "") or "").strip()
        key = f"{num}의{branch}" if branch and branch != "0" else num
        # 장·절 제목(전문) 행은 조문 내용이 "제1장 ..." 형태 — 실제 조문이 우선
        if key in index and art.get("is_heading"):
            continue
        index[key] = (art.get("article_title", "") or "", art.get("content", "") or "")
    return match["law_name"], index


async def _fetch_and_cache(key: str, law_name: str):
    """법령 조회 후 캐시에 저장한다. 요청자가 떠나도 끝까지 실행된다(shield)."""
    try:
        official, index = await _fetch_law_index(law_name)
        # await 없이 저장하므로 이벤트 루프 단일 스레드에서 원자적
        _law_index_cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, official, index)
        return official, index
    finally:
        _inflight.pop(key, None)


def _consume_task_exception(task: asyncio.Future) -> None:
    """아무도 기다리지 않는 작업의 예외로 'never retrieved' 경고가 나지 않게 한다."""
    if not task.cancelled():
        task.exception()


async def _get_law_index(law_name: str) -> tuple[str, dict[str, tuple[str, str]] | None]:
    """캐시를 거쳐 법령 조문 인덱스를 반환한다.

    - 같은 법령에 대한 동시 요청은 하나의 API 호출을 공유한다 (중복 다운로드 방지).
    - 공유 작업은 shield로 보호되어, 한 요청이 취소(클라이언트 이탈)돼도 다른 요청에 영향이 없다.
    - 대기 시간은 _FETCH_TIMEOUT_SECONDS로 제한한다 (초과 시 TimeoutError → 호출부에서 unverified).
    """
    key = _compact(law_name)
    async with _cache_lock:
        cached = _law_index_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1], cached[2]
        task = _inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(_fetch_and_cache(key, law_name))
            task.add_done_callback(_consume_task_exception)
            _inflight[key] = task

    return await asyncio.wait_for(asyncio.shield(task), timeout=_FETCH_TIMEOUT_SECONDS)


def _check_local(law_name: str, article: str) -> tuple[str, str] | None:
    """로컬 벡터 DB(laws 컬렉션)에서 조문 존재 여부를 확인한다 (동기).

    가지 조문은 "25의2" 형식으로 적재되어 있어 그대로 조회한다.
    """
    try:
        from data.vector_store import get_vector_store

        collection = get_vector_store().client.get_collection("laws")
        res = collection.get(
            where={"$and": [
                {"source": {"$eq": law_name}},
                {"article_number": {"$eq": article}},
            ]},
            limit=1,
            include=["documents", "metadatas"],
        )
        if res.get("ids"):
            meta = (res.get("metadatas") or [{}])[0] or {}
            doc = (res.get("documents") or [""])[0] or ""
            return meta.get("article_title", ""), doc
    except Exception as exc:  # 로컬 확인 실패는 치명적이지 않음
        logger.debug("citation_local_check_failed", law_name=law_name, error=str(exc))
    return None


def is_repealed(content: str) -> bool:
    """조문 본문이 '삭제'로 표시된 조문인지 판단한다."""
    return bool(_REPEALED_RE.match(content or ""))


def _law_url(law_name: str, article: str) -> str:
    """국가법령정보센터 조문 바로가기 URL ("15의2" → 제15조의2)"""
    from urllib.parse import quote

    main, _, branch = article.partition("의")
    label = f"제{main}조" + (f"의{branch}" if branch else "")
    return f"https://www.law.go.kr/법령/{quote(law_name)}/{quote(label)}"


def _make_excerpt(content: str, limit: int = 300) -> str:
    content = re.sub(r"\s+", " ", content or "").strip()
    return content[:limit] + ("…" if len(content) > limit else "")


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

async def _resolve_index(item: dict):
    """법령 후보를 순서대로 조회해 처음 찾은 법령의 (정식명, 인덱스)를 반환한다.

    사전에 있는 법령은 후보가 하나뿐이다. 모두 못 찾으면 (표시명, None).
    """
    for name in item.get("candidates") or [item["law_name"]]:
        official, index = await _get_law_index(name)
        if index is not None:
            return official, index
    return item["law_name"], None


async def _verify_one(item: dict, sem: asyncio.Semaphore) -> CitationCheck:
    law_name, article = item["law_name"], item["article"]
    check = CitationCheck(
        raw=item["raw"], law_name=law_name, article=article, status=STATUS_UNVERIFIED,
    )

    async with sem:
        try:
            official, index = await _resolve_index(item)
            if index is None:
                check.status = STATUS_UNKNOWN_LAW
                return check
            check.law_name = official
            check.law_url = _law_url(official, article)
            check.source = "law_api"
            if article in index:
                title, content = index[article]
                check.status = STATUS_REPEALED if is_repealed(content) else STATUS_VERIFIED
                check.article_title = title
                check.excerpt = _make_excerpt(content)
            else:
                check.status = STATUS_NOT_FOUND
            return check
        except Exception as exc:  # TimeoutError 포함
            logger.warning(
                "citation_api_check_failed",
                law_name=law_name, article=article, error=repr(exc),
            )

    # API 실패 → 로컬 벡터 DB로 대체 확인
    local = await asyncio.to_thread(_check_local, law_name, article)
    if local:
        check.article_title, content = local
        check.status = STATUS_REPEALED if is_repealed(content) else STATUS_VERIFIED
        check.excerpt = _make_excerpt(content)
        check.source = "local"
        check.law_url = _law_url(law_name, article)
    return check


async def verify_citations(answer: str) -> list[dict]:
    """답변 본문의 법령 인용을 추출·검증하여 결과 목록을 반환한다.

    실패해도 예외를 던지지 않고 가능한 결과만 반환한다.
    """
    items = extract_law_citations(answer)
    if not items:
        return []

    sem = asyncio.Semaphore(_CONCURRENCY)
    checks = await asyncio.gather(
        *[_verify_one(item, sem) for item in items], return_exceptions=True,
    )

    results: list[dict] = []
    for item, chk in zip(items, checks):
        if isinstance(chk, BaseException):
            logger.warning("citation_verify_error", item=item, error=str(chk))
            chk = CitationCheck(
                raw=item["raw"], law_name=item["law_name"],
                article=item["article"], status=STATUS_UNVERIFIED,
            )
        results.append(chk.to_dict())

    logger.info(
        "citation_verification_done",
        total=len(results),
        verified=sum(r["status"] == STATUS_VERIFIED for r in results),
        not_found=sum(r["status"] == STATUS_NOT_FOUND for r in results),
        repealed=sum(r["status"] == STATUS_REPEALED for r in results),
    )
    return results
