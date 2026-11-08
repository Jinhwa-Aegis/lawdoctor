"""분야 간 의견 대조 테스트 (LLM은 모킹)"""

import asyncio
import json

import pytest

from core import multi_perspective as mp
from core.classifier import analyze_query
from core.multi_perspective import (
    PerspectiveConfig,
    coordinator_prompt,
    coordinator_user_message,
    merge_balanced,
    opinions_text,
    parse_expert_opinion,
    select_domains,
)
from core.rag import _config as LEGAL_CONFIG
from models.chat import LegalCategory

CCTV_QUESTION = "아파트 관리사무소 CCTV 영상을 입주민이 보여달라고 하면 보여줘도 되나요? 관리업무를 우리 회사가 위탁받아 하고 있습니다."
CFG: PerspectiveConfig = LEGAL_CONFIG.perspective


# ---------------------------------------------------------------------------
# 분야 선택
# ---------------------------------------------------------------------------

def test_multi_domain_question_selects_two_domains():
    domains = select_domains(analyze_query(CCTV_QUESTION), CFG)
    assert domains == [LegalCategory.HOUSING, LegalCategory.PRIVACY]


def test_single_domain_question_skips():
    assert select_domains(analyze_query("장기수선충당금 사용 기준은?"), CFG) == []


def test_user_chosen_domain_skips():
    assert select_domains(analyze_query(CCTV_QUESTION), CFG, category_override=LegalCategory.PRIVACY) == []


def test_litigation_is_excluded():
    result = analyze_query("개인정보 유출로 분쟁이 생겼는데 개인정보 처리방침에 문제가 있나요?")
    domains = select_domains(result, CFG)
    assert LegalCategory.LITIGATION not in domains


# ---------------------------------------------------------------------------
# 균형 병합
# ---------------------------------------------------------------------------

def _res(ids):
    return {
        "ids": [ids], "documents": [[f"doc-{i}" for i in ids]],
        "metadatas": [[{"id": i} for i in ids]], "distances": [[0.1] * len(ids)],
    }


def test_merge_balanced_interleaves_and_dedupes():
    merged = merge_balanced([_res(["a1", "a2", "a3"]), _res(["b1", "a2", "b3"])], limit=5)
    assert merged["ids"][0] == ["a1", "b1", "a2", "a3", "b3"]
    assert merged["documents"][0][1] == "doc-b1"
    assert len(merged["metadatas"][0]) == 5


def test_merge_balanced_respects_limit_and_empty():
    assert merge_balanced([_res(["a1", "a2"]), _res(["b1", "b2"])], limit=3)["ids"][0] == ["a1", "b1", "a2"]
    assert merge_balanced([_res([]), _res([])], limit=3)["ids"][0] == []


# ---------------------------------------------------------------------------
# 전문가 응답 파싱
# ---------------------------------------------------------------------------

def test_parse_expert_opinion_normalizes():
    raw = "```json\n" + json.dumps({
        "verdict": "조건부 가능합니다 정말로 아주 긴 판단 문구",
        "risk": "HIGH",
        "conclusion": "정보주체 본인 영상만 열람 가능합니다 [1].",
        "key_points": ["a", "b", "c", "d"],
        "cautions": "타인 모자이크",
        "citations": ["개인정보 보호법 제35조"],
    }, ensure_ascii=False) + "\n```"
    op = parse_expert_opinion(raw)
    assert op["risk"] == "high"
    assert len(op["verdict"]) <= 20
    assert op["key_points"] == ["a", "b", "c"]
    assert op["cautions"] == ["타인 모자이크"]


@pytest.mark.parametrize("raw", ["", "그냥 문장", '{"verdict": "가능"}', "{깨진 json"])
def test_parse_expert_opinion_rejects_invalid(raw):
    assert parse_expert_opinion(raw) is None


# ---------------------------------------------------------------------------
# 조정자 프롬프트
# ---------------------------------------------------------------------------

OPINIONS = [
    {"domain": "housing", "label": "공동주택관리", "verdict": "가능", "risk": "low",
     "conclusion": "관리주체 판단으로 열람 가능", "key_points": ["관리규약"], "cautions": [], "citations": []},
    {"domain": "privacy", "label": "개인정보보호", "verdict": "조건부 가능", "risk": "high",
     "conclusion": "본인 영상만, 타인 비식별 필요", "key_points": ["개인정보 보호법 제35조"],
     "cautions": ["타인 모자이크"], "citations": ["개인정보 보호법 제35조"]},
]


def test_coordinator_prompt_has_table_columns_per_domain():
    prompt = coordinator_prompt("BASE", OPINIONS)
    assert prompt.startswith("BASE")
    assert "| 쟁점 | 공동주택관리 관점 | 개인정보보호 관점 | 정리 |" in prompt
    assert "|---|---|---|---|" in prompt
    assert "### 충돌·주의 지점" in prompt


def test_coordinator_user_message_prepends_opinions():
    msg = coordinator_user_message("참고자료...\n\n질문: Q", OPINIONS)
    assert msg.index("공동주택관리 검토 의견") < msg.index("개인정보보호 검토 의견") < msg.index("질문: Q")
    assert "판단: 조건부 가능 (위험도 high)" in msg


def test_opinions_text_collects_citations():
    assert "개인정보 보호법 제35조" in opinions_text(OPINIONS)


# ---------------------------------------------------------------------------
# 전문가 병렬 실행 — 실패한 분야는 제외
# ---------------------------------------------------------------------------

def test_run_experts_drops_failed_domain(monkeypatch):
    class FakeClient:
        async def generate(self, system_prompt, messages, max_tokens=0, model=None):
            if "개인정보보호" in system_prompt:
                raise RuntimeError("API 오류")
            return json.dumps({"verdict": "가능", "risk": "low", "conclusion": "가능합니다."}, ensure_ascii=False)

    monkeypatch.setattr(mp, "get_llm_client", lambda: FakeClient())
    opinions = asyncio.run(mp.run_experts(
        "Q", "CTX", [LegalCategory.HOUSING, LegalCategory.PRIVACY], CFG,
    ))
    assert [o["domain"] for o in opinions] == ["housing"]
    assert opinions[0]["label"] == "공동주택관리"


# ---------------------------------------------------------------------------
# 분야 필터 · 조문 단위 중복 제거
# ---------------------------------------------------------------------------

from core.multi_perspective import filter_by_sources


def _law_res(rows):
    """rows: [(id, source, article)]"""
    return {
        "ids": [[r[0] for r in rows]],
        "documents": [[f"doc-{r[0]}" for r in rows]],
        "metadatas": [[{"source": r[1], "article_number": r[2]} for r in rows]],
        "distances": [[0.1] * len(rows)],
    }


def test_filter_by_sources_drops_other_domain_laws():
    res = _law_res([("h1", "공동주택관리법", "93"), ("p1", "개인정보 보호법", "25"), ("h2", "주택법", "5")])
    out = filter_by_sources(res, ["공동주택관리법", "주택법"])
    assert out["ids"][0] == ["h1", "h2"]
    assert out["documents"][0] == ["doc-h1", "doc-h2"]


def test_filter_by_sources_keeps_original_when_nothing_matches():
    res = _law_res([("p1", "개인정보 보호법", "25")])
    assert filter_by_sources(res, ["공동주택관리법"])["ids"][0] == ["p1"]


def test_merge_dedupes_chunks_of_same_article_and_limits_per_domain():
    privacy = _law_res([
        ("p25a", "개인정보 보호법", "25"), ("p25b", "개인정보 보호법", "25"),
        ("p25c", "개인정보 보호법", "25"), ("p35", "개인정보 보호법", "35"), ("p18", "개인정보 보호법", "18"),
    ])
    housing = _law_res([("h93", "공동주택관리법", "93"), ("h27", "공동주택관리법", "27")])
    merged = merge_balanced([privacy, housing], limit=6, per_domain_limit=3)
    assert merged["ids"][0] == ["p25a", "h93", "h27", "p35", "p18"]


# ---------------------------------------------------------------------------
# 개념 검색
# ---------------------------------------------------------------------------

from core.legal_terms import concept_queries
from core.multi_perspective import append_unique


def test_concept_queries_short_and_unique():
    concepts = concept_queries(CCTV_QUESTION)
    assert "고정형 영상정보처리기기" in concepts
    assert "개인정보의 열람" in concepts
    assert len(concepts) == len(set(concepts)) and len(concepts) <= 4


def test_append_unique_adds_new_articles_only():
    base = _law_res([("p25a", "개인정보 보호법", "25"), ("h93", "공동주택관리법", "93")])
    extra1 = _law_res([("p25b", "개인정보 보호법", "25"), ("p35", "개인정보 보호법", "35"), ("p24", "개인정보 보호법", "24"), ("p40", "개인정보 보호법", "40")])
    extra2 = _law_res([("p35b", "개인정보 보호법", "35"), ("p17", "개인정보 보호법", "17")])
    out = append_unique(base, [extra1, extra2], per_extra=2)
    assert out["ids"][0] == ["p25a", "h93", "p35", "p24", "p17"]
    assert out["documents"][0][2] == "doc-p35"
