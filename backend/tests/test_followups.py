"""후속 질문 파싱 테스트"""

from core.followups import parse_followups


def test_parse_json_array():
    raw = '["위탁 계약서에 꼭 넣을 조항은?", "수탁자 교육은 어떻게 하나요?", "위반 시 과태료는?"]'
    assert parse_followups(raw) == [
        "위탁 계약서에 꼭 넣을 조항은?",
        "수탁자 교육은 어떻게 하나요?",
        "위반 시 과태료는?",
    ]


def test_parse_code_block_and_object():
    raw = '```json\n{"questions": ["질문 하나", "질문 둘"]}\n```'
    assert parse_followups(raw) == ["질문 하나?", "질문 둘?"]


def test_parse_numbered_lines_fallback():
    raw = "1. 첫 번째 질문인가요?\n2) 두 번째 질문\n- 세 번째 질문?\n4. 네 번째?"
    assert parse_followups(raw) == ["첫 번째 질문인가요?", "두 번째 질문?", "세 번째 질문?"]


def test_parse_dedup_and_empty():
    assert parse_followups('["같은 질문?", "같은 질문?", ""]') == ["같은 질문?"]
    assert parse_followups("") == []
