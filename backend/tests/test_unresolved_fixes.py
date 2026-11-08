"""화면 확인 후 미해결 건 회귀 테스트 — 분야 간 검색, 신뢰도 통합, 점검표 모순 보정"""

import pytest

from core.classifier import analyze_query
from core.confidence import combine_confidence, parse_stated_confidence
from core.contract_reviewer import ChecklistResult, normalize_checklist_results
from core.rag import _build_laws_where_filter
from models.chat import ConfidenceLevel, LegalCategory

CCTV_QUESTION = "아파트 관리사무소 CCTV 영상을 입주민이 보여달라고 하면 보여줘도 되나요? 관리업무를 우리 회사가 위탁받아 하고 있습니다."


# ---------------------------------------------------------------------------
# 1. 분야 간 검색 — 관련 분야 법령도 검색 대상에 포함
# ---------------------------------------------------------------------------

def _filter_law_names(where: dict | None) -> set[str] | None:
    if where is None:
        return None
    if "$or" in where:
        return {cond["source"]["$eq"] for cond in where["$or"]}
    return {where["source"]["$eq"]}


def test_cctv_question_includes_privacy_laws():
    result = analyze_query(CCTV_QUESTION)
    assert result.category == LegalCategory.HOUSING
    assert LegalCategory.PRIVACY in result.related_categories

    names = _filter_law_names(_build_laws_where_filter(result))
    assert {"공동주택관리법", "주택법", "개인정보 보호법"} <= names


def test_single_domain_question_keeps_narrow_filter():
    result = analyze_query("장기수선충당금 사용 기준은?")
    assert result.related_categories == []
    assert _filter_law_names(_build_laws_where_filter(result)) == {"공동주택관리법", "주택법"}


def test_related_litigation_removes_filter():
    """관련 분야에 '전체 검색' 분야(소송)가 있으면 필터를 걸지 않는다."""
    result = analyze_query("개인정보 유출로 분쟁이 생겼는데 개인정보 처리방침에 문제가 있나요?")
    assert LegalCategory.LITIGATION in [result.category, *result.related_categories]
    assert _build_laws_where_filter(result) is None


# ---------------------------------------------------------------------------
# 2. 신뢰도 통합
# ---------------------------------------------------------------------------

ANSWER_TEMPLATE = """### 결론
가능합니다.

### 근거
개인정보 보호법 제25조 ...

### 신뢰도
{body}
"""


@pytest.mark.parametrize("body, level, reason_part", [
    ("**높음**. 관련 법령의 명확한 규정에 따라 판단했습니다.", ConfidenceLevel.HIGH, "관련 법령의 명확한"),
    ("보통 — 해석이 갈릴 수 있습니다.", ConfidenceLevel.MEDIUM, "해석이 갈릴"),
    ("**낮음**: 관련 판례가 없습니다.", ConfidenceLevel.LOW, "관련 판례가 없습니다"),
])
def test_parse_stated_confidence(body, level, reason_part):
    stated, reason = parse_stated_confidence(ANSWER_TEMPLATE.format(body=body))
    assert stated == level
    assert reason_part in reason


def test_parse_stated_confidence_missing_section():
    assert parse_stated_confidence("### 결론\n답변") == (None, "")


def test_combine_takes_lowest_signal():
    level, adj = combine_confidence(ConfidenceLevel.MEDIUM, ConfidenceLevel.HIGH, [])
    assert level == ConfidenceLevel.MEDIUM and adj == []

    level, adj = combine_confidence(ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, [])
    assert level == ConfidenceLevel.MEDIUM and "AI 자체 평가 반영" in adj


def test_combine_problem_citation_forces_low():
    cites = [{"status": "verified"}, {"status": "repealed"}]
    level, adj = combine_confidence(ConfidenceLevel.HIGH, ConfidenceLevel.HIGH, cites)
    assert level == ConfidenceLevel.LOW
    assert "확인되지 않는 조문 인용" in adj


def test_combine_uncertain_citation_caps_medium():
    level, _ = combine_confidence(ConfidenceLevel.HIGH, None, [{"status": "unverified"}])
    assert level == ConfidenceLevel.MEDIUM
    level, _ = combine_confidence(ConfidenceLevel.LOW, None, [{"status": "unverified"}])
    assert level == ConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# 4. 점검표 판정 모순 보정
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("comment, expected_status, adjusted", [
    ("당사자는 명확하나, 을의 입장에서 불리한 조항들이 있음.", "risk", True),
    ("을만 의무를 부담하는 일방적 구조임.", "risk", True),
    ("관할 조항이 당사에 불리하지 않음.", "ok", False),
    ("기간이 과도하지 않고 적절함.", "ok", False),
    ("계약 기간이 명확히 규정됨.", "ok", False),
])
def test_ok_with_negative_comment_is_adjusted(comment, expected_status, adjusted):
    raw = [ChecklistResult(item_id="parties", status="ok", comment=comment)]
    result = {r.item_id: r for r in normalize_checklist_results("nda", raw)}
    assert result["parties"].status == expected_status
    assert result["parties"].auto_adjusted is adjusted


def test_non_ok_status_is_not_touched():
    raw = [ChecklistResult(item_id="nda_return", status="missing", comment="불리함")]
    result = {r.item_id: r for r in normalize_checklist_results("nda", raw)}
    assert result["nda_return"].status == "missing"
    assert result["nda_return"].auto_adjusted is False


# ---------------------------------------------------------------------------
# 1-1. 일상어 → 법령 용어 검색 보강 / 가지 조문 표기
# ---------------------------------------------------------------------------

from core.legal_terms import expand_legal_terms
from data.law_api import article_label


def test_expand_cctv_to_statutory_term():
    expanded = expand_legal_terms(CCTV_QUESTION)
    assert expanded.startswith(CCTV_QUESTION)
    assert "고정형 영상정보처리기기" in expanded


def test_expand_no_duplicates_and_noop():
    q = "CCTV와 cctv 그리고 고정형 영상정보처리기기"
    assert expand_legal_terms(q) == q                       # 이미 법령 용어 포함
    assert expand_legal_terms("장기수선충당금 사용 기준은?") == "장기수선충당금 사용 기준은?"


def test_expansion_does_not_change_classification():
    """보강은 검색에만 적용 — 분류는 원문 기준으로 공동주택이 유지돼야 한다."""
    assert analyze_query(CCTV_QUESTION).category == LegalCategory.HOUSING


@pytest.mark.parametrize("num, label", [("15", "제15조"), ("25의2", "제25조의2"), ("39의3", "제39조의3")])
def test_article_label(num, label):
    assert article_label(num) == label


# ---------------------------------------------------------------------------
# 사용자가 직접 고른 분야 (category override)
# ---------------------------------------------------------------------------

from core.rag_pipeline import apply_category_override


def test_category_override_keeps_auto_category_as_related():
    auto = analyze_query(CCTV_QUESTION)                       # housing (+ privacy)
    forced = apply_category_override(auto, LegalCategory.PRIVACY)
    assert forced.category == LegalCategory.PRIVACY
    assert LegalCategory.HOUSING in forced.related_categories
    assert LegalCategory.PRIVACY not in forced.related_categories
    names = _filter_law_names(_build_laws_where_filter(forced))
    assert {"개인정보 보호법", "공동주택관리법"} <= names


def test_category_override_none_is_noop():
    auto = analyze_query(CCTV_QUESTION)
    assert apply_category_override(auto, None) is auto
