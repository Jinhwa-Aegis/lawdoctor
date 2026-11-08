"""조항 위치 찾기 테스트"""

from core.clause_locator import locate_clause
from core.contract_reviewer import ContractReviewResult, RiskItem, attach_clause_spans

CONTRACT = """비밀유지계약서

제1조(목적) 본 계약은 본 사업 검토를 위하여 갑이 을에게 제공하는 정보의 비밀유지에 관한 사항을 정함을 목적으로 한다.

제2조(비밀정보) 비밀정보란 갑이 을에게 제공하는 일체의 정보로서,
서면, 구두, 전자적 형태를 불문하며 비밀 표시 여부와 관계없이 모든 정보를 말한다.

제5조(위약벌) 을이 본 계약을 위반한 경우, 을은 갑에게 위약벌로 금 5억원을 지급하여야 하며, 갑은 이와 별도로 실제 손해 전부의 배상을 청구할 수 있다. 제2조에 따른 정보에도 적용한다.

제6조(관할) 본 계약과 관련한 분쟁은 갑의 본점 소재지를 관할하는 법원을 전속관할로 한다.
"""


def _sub(span):
    return CONTRACT[span.start:span.end]


def test_exact_match_ignores_line_breaks_and_spaces():
    quote = "비밀정보란 갑이 을에게 제공하는 일체의 정보로서, 서면, 구두, 전자적 형태를 불문하며"
    span = locate_clause(CONTRACT, quote)
    assert span.method == "exact"
    assert _sub(span).startswith("비밀정보란")
    assert _sub(span).endswith("불문하며")


def test_quote_decorations_are_stripped():
    span = locate_clause(CONTRACT, "“을은 갑에게 위약벌로 금 5억원을 지급하여야 하며…”")
    assert span is not None and "5억원" in _sub(span)


def test_prefix_match_when_ai_paraphrases_the_end():
    quote = "을이 본 계약을 위반한 경우, 을은 갑에게 위약벌로 금 5억원을 지급하고 손해를 배상한다."
    span = locate_clause(CONTRACT, quote)
    assert span.method == "prefix"
    assert _sub(span).startswith("을이 본 계약을 위반한 경우")


def test_article_fallback_uses_heading_not_inline_reference():
    """원문 인용이 없으면 조항 번호로 찾는다. 본문 속 '제2조에 따른'은 조항 제목이 아니다."""
    span = locate_clause(CONTRACT, None, "제2조(비밀정보)")
    assert span.method == "article"
    assert _sub(span).startswith("제2조(비밀정보)")
    assert _sub(span).endswith("모든 정보를 말한다.")


def test_last_article_until_end():
    span = locate_clause(CONTRACT, "", "제6조(관할)")
    assert _sub(span).endswith("전속관할로 한다.")


def test_not_found_returns_none():
    assert locate_clause(CONTRACT, "존재하지 않는 조항 문구입니다 확인용", "제99조") is None
    assert locate_clause("", "아무 문구", "제1조") is None


def test_attach_clause_spans_sets_offsets():
    result = ContractReviewResult(
        contract_type="NDA", summary="", overall_risk="high", recommendation="",
        missing_clauses=[], contract_text=CONTRACT,
        risk_items=[
            RiskItem(clause="제5조(위약벌)", risk_level="high", description="d",
                     original_text="을은 갑에게 위약벌로 금 5억원을 지급하여야 하며"),
            RiskItem(clause="제9조(없음)", risk_level="low", description="d", original_text="없는 문구 테스트 입니다"),
        ],
    )
    attach_clause_spans(result)
    first, second = result.risk_items
    assert CONTRACT[first.span_start:first.span_end].startswith("을은 갑에게")
    assert second.span_start is None and second.span_end is None
