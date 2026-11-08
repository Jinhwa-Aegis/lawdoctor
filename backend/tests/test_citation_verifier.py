"""인용 추출·검증 로직 테스트 (외부 API는 모킹)"""

import asyncio

import pytest

from core import citation_verifier as cv
from core.citation_verifier import (
    extract_law_citations,
    resolve_law_name,
    verify_citations,
)


# ---------------------------------------------------------------------------
# 법령명 해석
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("candidate, expected", [
    ("개인정보 보호법", "개인정보 보호법"),
    ("개인정보보호법", "개인정보 보호법"),                    # 약칭(공백 없음)
    ("정보통신망법", "정보통신망 이용촉진 및 정보보호 등에 관한 법률"),
    ("따라서 민법", "민법"),                                  # 앞 단어 제거
    ("이 경우 공동주택관리법", "공동주택관리법"),
    ("개인정보 보호법 시행령", "개인정보 보호법 시행령"),
])
def test_resolve_known_law_names(candidate, expected):
    name, known = resolve_law_name(candidate)
    assert name == expected
    assert known is True


def test_resolve_unknown_law_strips_particles():
    name, known = resolve_law_name("이에 따라 가상의특별법")
    assert name == "가상의특별법"
    assert known is False


# ---------------------------------------------------------------------------
# 인용 추출
# ---------------------------------------------------------------------------

def test_extract_basic_and_branch_articles():
    text = (
        "개인정보 보호법 제15조 제1항에 따라 동의를 받아야 합니다. "
        "또한 개인정보 보호법 제39조의3도 확인하십시오."
    )
    items = extract_law_citations(text)
    assert [(i["law_name"], i["article"]) for i in items] == [
        ("개인정보 보호법", "15"),
        ("개인정보 보호법", "39의3"),
    ]


def test_extract_handles_markdown_and_spacing():
    text = "**민법 제 750 조**(불법행위)와 **상법** 제 24조를 참고"
    items = extract_law_citations(text)
    assert ("민법", "750") in [(i["law_name"], i["article"]) for i in items]


@pytest.mark.parametrize("text", [
    '"개인정보 보호법" 제15조 제1항에 따라',     # 실제 gpt-4o 출력 형태
    "「개인정보 보호법」 제15조에 따라",          # 법률 문서 관례
    "『개인정보 보호법』제15조",
    "“개인정보 보호법” 제15조",
])
def test_extract_quoted_law_names(text):
    items = extract_law_citations(text)
    assert [(i["law_name"], i["article"]) for i in items] == [("개인정보 보호법", "15")]


def test_extract_same_law_reference():
    text = "공동주택관리법 제18조에 규정되어 있고, 같은 법 제19조도 적용됩니다."
    items = extract_law_citations(text)
    assert [(i["law_name"], i["article"]) for i in items] == [
        ("공동주택관리법", "18"),
        ("공동주택관리법", "19"),
    ]


def test_extract_deduplicates():
    text = "민법 제390조 ... 민법 제390조 ... 민법 제393조"
    items = extract_law_citations(text)
    assert [i["article"] for i in items] == ["390", "393"]


def test_extract_no_citation():
    assert extract_law_citations("법령 인용이 없는 일반 문장입니다.") == []


# ---------------------------------------------------------------------------
# 검증 (국가법령정보센터 응답 모킹)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    # 테스트마다 새 이벤트 루프를 쓰므로 락·진행 중 작업도 초기화
    monkeypatch.setattr(cv, "_cache_lock", asyncio.Lock())
    cv._inflight.clear()
    cv._law_index_cache.clear()
    yield
    cv._inflight.clear()
    cv._law_index_cache.clear()


def test_concurrent_requests_share_one_fetch(monkeypatch):
    calls = []

    async def slow_fetch(law_name):
        calls.append(law_name)
        await asyncio.sleep(0.05)
        return law_name, {"15": ("제목", "내용"), "26": ("제목", "내용"), "39의3": ("제목", "내용")}

    monkeypatch.setattr(cv, "_fetch_law_index", slow_fetch)
    results = asyncio.run(verify_citations(
        "개인정보 보호법 제15조, 같은 법 제26조, 개인정보 보호법 제39조의3"
    ))
    assert [r["status"] for r in results] == [cv.STATUS_VERIFIED] * 3
    assert calls == ["개인정보 보호법"]


def test_verify_statuses(monkeypatch):
    async def fake_fetch(law_name):
        if law_name == "개인정보 보호법":
            return "개인정보 보호법", {"15": ("개인정보의 수집ㆍ이용", "① 개인정보처리자는 ...")}
        return law_name, None  # 존재하지 않는 법령

    monkeypatch.setattr(cv, "_fetch_law_index", fake_fetch)

    text = "개인정보 보호법 제15조, 개인정보 보호법 제999조, 가상의특별법 제1조"
    results = asyncio.run(verify_citations(text))
    status = {(r["law_name"], r["article"]): r["status"] for r in results}

    assert status[("개인정보 보호법", "15")] == cv.STATUS_VERIFIED
    assert status[("개인정보 보호법", "999")] == cv.STATUS_NOT_FOUND
    assert status[("가상의특별법", "1")] == cv.STATUS_UNKNOWN_LAW

    verified = next(r for r in results if r["status"] == cv.STATUS_VERIFIED)
    assert verified["article_title"] == "개인정보의 수집ㆍ이용"
    assert verified["law_url"].startswith("https://www.law.go.kr/")


def test_verify_api_failure_falls_back_to_local(monkeypatch):
    async def failing_fetch(law_name):
        raise RuntimeError("API 장애")

    monkeypatch.setattr(cv, "_fetch_law_index", failing_fetch)
    monkeypatch.setattr(
        cv, "_check_local",
        lambda law, art: ("손해배상의 범위", "채무불이행으로 인한 ...") if art == "393" else None,
    )

    results = asyncio.run(verify_citations("민법 제393조와 민법 제394조"))
    status = {r["article"]: (r["status"], r["source"]) for r in results}
    assert status["393"] == (cv.STATUS_VERIFIED, "local")
    assert status["394"][0] == cv.STATUS_UNVERIFIED


def test_verify_uses_cache(monkeypatch):
    calls = []

    async def fake_fetch(law_name):
        calls.append(law_name)
        return law_name, {"1": ("목적", "...")}

    monkeypatch.setattr(cv, "_fetch_law_index", fake_fetch)
    asyncio.run(verify_citations("민법 제1조"))
    asyncio.run(verify_citations("민법 제1조"))
    assert calls == ["민법"]


# ---------------------------------------------------------------------------
# 삭제 조문 / 조문 본문 조립
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content, expected", [
    ("제22조 삭제 <2020. 2. 4.>", True),
    ("제22조의2 삭제 <2020.2.4>", True),
    ("제15조(개인정보의 수집ㆍ이용)\n① 개인정보처리자는 ...", False),
    ("제3조(정의) 이 법에서 \"삭제\"란 ...", False),
])
def test_is_repealed(content, expected):
    assert cv.is_repealed(content) is expected


def test_verify_repealed_article(monkeypatch):
    async def fake_fetch(law_name):
        return law_name, {"22": ("", "제22조 삭제 <2020. 2. 4.>")}

    monkeypatch.setattr(cv, "_fetch_law_index", fake_fetch)
    results = asyncio.run(verify_citations("정보통신망법 제22조"))
    assert results[0]["status"] == cv.STATUS_REPEALED


def test_collect_article_text_includes_paragraphs():
    import xml.etree.ElementTree as ET
    from data.law_api import _collect_article_text

    xml = (
        "<조문단위><조문내용>제15조(개인정보의 수집ㆍ이용)</조문내용>"
        "<항><항내용>① 개인정보처리자는 다음 각 호의 경우 수집할 수 있다.</항내용>"
        "<호><호내용>1. 정보주체의 동의를 받은 경우</호내용>"
        "<목><목내용>가. 세부 사항</목내용></목></호></항>"
        "<항><항내용>② 동의를 받을 때에는 알려야 한다.</항내용></항></조문단위>"
    )
    text = _collect_article_text(ET.fromstring(xml))
    assert text.splitlines() == [
        "제15조(개인정보의 수집ㆍ이용)",
        "① 개인정보처리자는 다음 각 호의 경우 수집할 수 있다.",
        "1. 정보주체의 동의를 받은 경우",
        "가. 세부 사항",
        "② 동의를 받을 때에는 알려야 한다.",
    ]


# ---------------------------------------------------------------------------
# 코드 리뷰 지적 사항 회귀 테스트
# ---------------------------------------------------------------------------

def test_unknown_law_does_not_swallow_preceding_words():
    """H1: 사전에 없는 법령명 앞의 단어가 법령명에 섞이면 안 된다."""
    items = extract_law_citations("퇴직금은 지급해야 하며 근로자퇴직급여 보장법 제8조에 따릅니다.")
    assert len(items) == 1
    assert items[0]["law_name"] == "근로자퇴직급여 보장법"
    # API 후보는 긴 것부터, 정확한 이름을 포함
    assert "근로자퇴직급여 보장법" in items[0]["candidates"]


@pytest.mark.parametrize("text", [
    "관련 법령 제15조를 확인하세요.",
    "회사 취업규칙 제10조에 따라",
    "해당 법률 제3조",
])
def test_generic_nouns_are_not_citations(text):
    """H1: 일반 명사(관련 법령, 취업규칙)는 인용으로 보지 않는다."""
    assert extract_law_citations(text) == []


def test_unknown_law_resolves_via_candidate_api_lookup(monkeypatch):
    """H1: 후보를 차례로 조회해 정확히 일치하는 법령을 찾는다."""
    async def fake_fetch(law_name):
        if law_name == "근로자퇴직급여 보장법":
            return law_name, {"8": ("퇴직금제도의 설정 등", "① 퇴직금제도를 설정하려는 사용자는 ...")}
        return law_name, None

    monkeypatch.setattr(cv, "_fetch_law_index", fake_fetch)
    results = asyncio.run(verify_citations("지급해야 하며 근로자퇴직급여 보장법 제8조"))
    assert results[0]["status"] == cv.STATUS_VERIFIED
    assert results[0]["law_name"] == "근로자퇴직급여 보장법"


def test_same_law_enforcement_decree():
    """M3: '같은 법 시행령'은 직전 법령의 시행령이다."""
    items = extract_law_citations("개인정보 보호법 제26조와 같은 법 시행령 제28조")
    assert [(i["law_name"], i["article"]) for i in items] == [
        ("개인정보 보호법", "26"),
        ("개인정보 보호법 시행령", "28"),
    ]


@pytest.mark.parametrize("text", [
    "**개인정보 보호법** 제15조",
    "__개인정보 보호법__ 제15조",
    "`개인정보 보호법` 제15조",
])
def test_markdown_emphasis_around_law_name(text):
    """M4: 마크다운 강조로 감싼 법령명도 추출한다."""
    items = extract_law_citations(text)
    assert [(i["law_name"], i["article"]) for i in items] == [("개인정보 보호법", "15")]


def test_continuation_articles_after_comma():
    """L6: '민법 제393조, 제398조'의 두 번째 조문도 추출한다."""
    items = extract_law_citations("민법 제393조, 제398조 및 제750조를 참고하고 상법 제24조도 확인")
    assert [(i["law_name"], i["article"]) for i in items] == [
        ("민법", "393"), ("민법", "398"), ("민법", "750"), ("상법", "24"),
    ]


def test_continuation_skips_paragraph_numbers():
    items = extract_law_citations("개인정보 보호법 제15조 제1항 및 제17조")
    assert [i["article"] for i in items] == ["15", "17"]


def test_law_url_for_branch_article():
    """L1: 가지 조문 링크는 '제15조의2' 형태여야 한다."""
    from urllib.parse import unquote
    url = unquote(cv._law_url("개인정보 보호법", "39의3"))
    assert url.endswith("/개인정보 보호법/제39조의3")
    assert unquote(cv._law_url("민법", "750")).endswith("/민법/제750조")


def test_local_fallback_detects_repealed(monkeypatch):
    """L2: 로컬 대체 확인에서도 삭제 조문을 구분한다."""
    async def failing_fetch(law_name):
        raise RuntimeError("API 장애")

    monkeypatch.setattr(cv, "_fetch_law_index", failing_fetch)
    monkeypatch.setattr(cv, "_check_local", lambda law, art: ("", "제22조 삭제 <2020.2.4>"))
    results = asyncio.run(verify_citations("정보통신망법 제22조"))
    assert (results[0]["status"], results[0]["source"]) == (cv.STATUS_REPEALED, "local")


def test_cancelled_requester_does_not_cancel_shared_fetch(monkeypatch):
    """M1: 한 요청이 취소돼도 공유 다운로드는 끝까지 실행되어 캐시된다."""
    async def slow_fetch(law_name):
        await asyncio.sleep(0.1)
        return law_name, {"1": ("목적", "...")}

    monkeypatch.setattr(cv, "_fetch_law_index", slow_fetch)

    async def scenario():
        first = asyncio.ensure_future(cv._get_law_index("민법"))
        await asyncio.sleep(0.01)
        second = asyncio.ensure_future(cv._get_law_index("민법"))
        await asyncio.sleep(0.01)
        first.cancel()                      # 첫 요청자 이탈
        official, index = await second      # 두 번째 요청자는 정상 결과
        return official, index

    official, index = asyncio.run(scenario())
    assert index == {"1": ("목적", "...")}
    assert "민법" in cv._law_index_cache


def test_slow_api_times_out_as_unverified(monkeypatch):
    """M2: 법령 API가 느리면 기다리지 않고 미검증 처리한다."""
    async def hanging_fetch(law_name):
        await asyncio.sleep(5)
        return law_name, {"1": ("", "")}

    monkeypatch.setattr(cv, "_fetch_law_index", hanging_fetch)
    monkeypatch.setattr(cv, "_FETCH_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(cv, "_check_local", lambda law, art: None)
    results = asyncio.run(verify_citations("민법 제1조"))
    assert results[0]["status"] == cv.STATUS_UNVERIFIED
