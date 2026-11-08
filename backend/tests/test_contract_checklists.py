"""계약 유형별 점검표 및 리뷰 결과 정규화 테스트"""

import json

import pytest

from core.contract_checklists import (
    CONTRACT_TYPES,
    format_checklist_prompt,
    get_checklist,
    list_contract_types,
    parse_detected_type,
)
from core.contract_reviewer import (
    ChecklistResult,
    _parse_review_response,
    normalize_checklist_results,
)


def test_checklist_ids_are_unique_per_type():
    for key in CONTRACT_TYPES:
        ids = [item.id for item in get_checklist(key)]
        assert len(ids) == len(set(ids)), key


def test_list_contract_types_shape():
    types = list_contract_types()
    keys = {t["key"] for t in types}
    assert {"nda", "service", "saas", "privacy_outsourcing", "housing_management", "lease", "general"} <= keys
    assert all(t["item_count"] > 0 and t["label"] for t in types)


def test_format_prompt_includes_all_item_ids():
    prompt = format_checklist_prompt("privacy_outsourcing")
    for item in get_checklist("privacy_outsourcing"):
        assert f"[{item.id}]" in prompt
    assert "개인정보 보호법 제26조" in prompt


@pytest.mark.parametrize("raw, expected", [
    ("nda", "nda"),
    ("  SaaS \n", "saas"),
    ("유형: privacy_outsourcing", "privacy_outsourcing"),
    ("모르겠습니다", "general"),
    ("", "general"),
])
def test_parse_detected_type(raw, expected):
    assert parse_detected_type(raw) == expected


def test_normalize_orders_fills_and_drops():
    raw = [
        ChecklistResult(item_id="nda_return", status="missing", comment="반환 조항 없음"),
        ChecklistResult(item_id="nda_definition", status="ok"),
        ChecklistResult(item_id="unknown_item", status="ok"),      # 점검표에 없음 → 제외
        ChecklistResult(item_id="nda_purpose", status="weird"),    # 잘못된 상태 → na
    ]
    result = normalize_checklist_results("nda", raw)
    ids = [r.item_id for r in result]

    assert ids == [item.id for item in get_checklist("nda")]
    by_id = {r.item_id: r for r in result}
    assert by_id["nda_definition"].status == "ok"
    assert by_id["nda_definition"].name == "비밀정보의 정의·범위"
    assert by_id["nda_return"].status == "missing"
    assert by_id["nda_purpose"].status == "na"
    assert by_id["nda_penalty"].status == "na"                     # AI가 빠뜨린 항목
    assert by_id["nda_penalty"].legal_basis == "민법 제398조"
    assert "unknown_item" not in by_id


def test_parse_review_response_with_new_fields():
    payload = {
        "contract_type": "NDA",
        "our_position": "정보 수령자(을)",
        "summary": "요약",
        "risk_items": [{
            "clause": "제7조(위약벌)",
            "risk_level": "high",
            "risk_score": 85,
            "description": "과도한 위약벌",
            "legal_basis": "민법 제398조",
            "original_text": "위반 시 금 1억원을 지급한다.",
            "revised_text": "위반 시 실제 발생한 손해를 배상한다.",
        }],
        "missing_clauses": [{"clause_name": "반환·파기", "importance": "medium", "description": "필요"}],
        "checklist_results": [{"item_id": "nda_penalty", "status": "risk", "comment": "1억원"}, "잘못된 항목"],
        "overall_risk": "high",
        "recommendation": "수정 후 체결",
    }
    result = _parse_review_response("```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```")
    assert result.our_position == "정보 수령자(을)"
    assert result.risk_items[0].risk_score == 85
    assert result.risk_items[0].revised_text.startswith("위반 시 실제")
    assert [c.item_id for c in result.checklist_results] == ["nda_penalty"]


def test_parse_review_response_legacy_format_still_works():
    payload = {
        "contract_type": "위탁계약", "summary": "s",
        "risk_items": [{"clause": "c", "risk_level": "low", "description": "d", "legal_basis": "민법"}],
        "missing_clauses": [], "overall_risk": "low", "recommendation": "r",
    }
    result = _parse_review_response(json.dumps(payload, ensure_ascii=False))
    assert result.risk_items[0].risk_score is None
    assert result.checklist_results == []


# ---------------------------------------------------------------------------
# 코드 리뷰 지적 사항 회귀 테스트
# ---------------------------------------------------------------------------

def test_null_fields_do_not_discard_review():
    """H2: LLM이 일부 필드를 null로 내도 리뷰 전체가 오류 처리되면 안 된다."""
    payload = {
        "contract_type": "NDA", "summary": "요약", "our_position": None,
        "risk_items": [
            {"clause": "제5조", "risk_level": "high", "description": "과도", "legal_basis": None,
             "risk_score": "85점", "original_text": None, "revised_text": "수정안"},
            {"clause": "제6조", "risk_level": "medium", "description": "관할", "legal_basis": "민사소송법",
             "risk_score": 120},
            "문자열 항목",                                  # 형식 오류 항목 → 건너뜀
            {"risk_level": "low"},                          # 필수 필드 누락 → 건너뜀
        ],
        "missing_clauses": None,
        "checklist_results": [{"item_id": "nda_return", "status": "missing", "comment": None, "clause_ref": None}],
        "overall_risk": "high", "recommendation": None,
    }
    result = _parse_review_response(json.dumps(payload, ensure_ascii=False))

    assert result.summary == "요약"                          # 오류 폴백이 아님
    assert [r.clause for r in result.risk_items] == ["제5조", "제6조"]
    assert result.risk_items[0].legal_basis == ""
    assert result.risk_items[0].risk_score is None           # "85점"은 숫자로 해석 불가
    assert result.risk_items[1].risk_score == 100            # 범위 보정
    assert result.missing_clauses == []
    assert result.checklist_results[0].comment == ""
    assert result.recommendation == ""
    assert result.our_position == ""


@pytest.mark.parametrize("raw, expected", [
    ("nda입니다", "nda"),
    ("유형은 saas예요", "saas"),
    ("lease_x", "general"),   # 다른 식별자의 일부는 무시
])
def test_parse_detected_type_korean_suffix(raw, expected):
    """L5: 한글이 바로 붙어도 유형 키를 인식한다."""
    assert parse_detected_type(raw) == expected
