"""분야 간 의견 대조 — 복수 분야에 걸친 질의를 분야별로 검토한 뒤 대조·종합한다

흐름:
1. 분야 선택: 자동 분류의 주 분야 + 관련 분야가 2개 이상일 때만 동작
   (사용자가 분야를 직접 고르면 그 분야만 답한다)
2. 분야별 균형 검색: 분야마다 법령을 따로 검색해 합친다 (한 분야가 근거를 독식하지 않도록)
3. 분야별 검토: 분야 전문가 역할 LLM을 병렬 실행 → 한 줄 판단·위험도·핵심 근거·인용 조문(JSON)
4. 종합: 조정자 역할 LLM이 의견을 합치지 않고 '대조'하여 공통 결론과 충돌 지점을 정리
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
import structlog

from core.llm import get_llm_client

logger = structlog.get_logger(__name__)

_EXPERT_TIMEOUT_SECONDS = 30.0
_EXPERT_MAX_TOKENS = 700
_VALID_RISKS = {"high", "medium", "low"}


@dataclass(frozen=True)
class PerspectiveConfig:
    """분야 간 의견 대조 설정 (도메인별로 주입)"""

    labels: dict                      # 분야 Enum → 표시 이름 (예: PRIVACY → "개인정보보호")
    focus: dict                       # 분야 Enum → 검토 관점 설명 (적용 법령 등)
    law_collection: str               # 분야별로 나눠 검색할 컬렉션 이름
    excluded: set = field(default_factory=set)  # 대조에서 제외할 분야 (예: 소송)
    max_domains: int = 3
    per_domain_results: int = 3       # 분야별로 컨텍스트에 넣을 법령 조문 수
    per_domain_fetch: int = 8         # 분야별 검색 시 가져올 후보 수 (중복 조문 제거 전)
    domain_sources: dict = field(default_factory=dict)  # 분야 Enum → 해당 분야 법령명 목록


# ---------------------------------------------------------------------------
# 1. 분야 선택
# ---------------------------------------------------------------------------

def select_domains(classification, cfg: PerspectiveConfig, category_override=None) -> list:
    """의견 대조에 참여할 분야 목록. 2개 미만이면 빈 목록(단일 답변)."""
    if category_override is not None:
        return []
    candidates = [classification.category, *getattr(classification, "related_categories", [])]
    domains: list = []
    for c in candidates:
        if c in cfg.labels and c not in cfg.excluded and c not in domains:
            domains.append(c)
    domains = domains[: cfg.max_domains]
    return domains if len(domains) >= 2 else []


# ---------------------------------------------------------------------------
# 2. 분야별 균형 검색 결과 병합
# ---------------------------------------------------------------------------

def filter_by_sources(result: dict, sources: list[str]) -> dict:
    """분야 법령만 남긴다. 하이브리드 검색의 BM25가 메타데이터 필터를 적용하지 않아
    다른 분야 법령이 섞이기 때문이다. 걸러서 아무것도 남지 않으면 원래 결과를 쓴다."""
    if not sources or not result.get("metadatas"):
        return result
    metas = result["metadatas"][0]
    keep = [i for i, m in enumerate(metas) if (m or {}).get("source") in sources]
    if not keep:
        return result
    out = {}
    for key in ("ids", "documents", "metadatas", "distances"):
        if result.get(key):
            out[key] = [[result[key][0][i] for i in keep]]
    return out


def _dedupe_key(doc_id, meta: dict):
    """같은 조문의 여러 청크는 하나로 본다 (법령명 + 조 번호)."""
    meta = meta or {}
    if meta.get("source") and meta.get("article_number"):
        return ("article", meta["source"], str(meta["article_number"]))
    return ("id", doc_id)


def append_unique(base: dict, extras: list[dict], per_extra: int) -> dict:
    """기존 검색 결과 뒤에, 추가 검색 결과마다 아직 없는 조문을 최대 per_extra건씩 붙인다.

    같은 조문(법령명+조 번호)의 다른 청크는 중복으로 본다.
    """
    def rows(r: dict):
        ids = (r.get("ids") or [[]])[0]
        docs = (r.get("documents") or [[]])[0]
        metas = (r.get("metadatas") or [[]])[0] if r.get("metadatas") else [{}] * len(ids)
        dists = (r.get("distances") or [[]])[0] if r.get("distances") else [0.0] * len(ids)
        return list(zip(ids, docs, metas, dists))

    merged_rows = rows(base)
    seen = {_dedupe_key(i, m) for i, _, m, _ in merged_rows}
    for extra in extras:
        added = 0
        for doc_id, doc, meta, dist in rows(extra):
            if added >= per_extra:
                break
            key = _dedupe_key(doc_id, meta)
            if key in seen:
                continue
            seen.add(key)
            merged_rows.append((doc_id, doc, meta, dist))
            added += 1
    return {
        "ids": [[r[0] for r in merged_rows]],
        "documents": [[r[1] for r in merged_rows]],
        "metadatas": [[r[2] for r in merged_rows]],
        "distances": [[r[3] for r in merged_rows]],
    }


def merge_balanced(per_domain: list[dict], limit: int, per_domain_limit: int | None = None) -> dict:
    """분야별 검색 결과를 번갈아 가며 합친다.

    - 같은 조문(법령명+조 번호)의 여러 청크는 가장 순위가 높은 하나만 남긴다
    - 분야별로 최대 per_domain_limit건, 전체 최대 limit건

    Args:
        per_domain: 분야 순서대로의 ChromaDB 형식 결과 {"ids": [[...]], "documents": [[...]], ...}
    """
    columns = [
        (
            (r.get("ids") or [[]])[0],
            (r.get("documents") or [[]])[0],
            (r.get("metadatas") or [[]])[0] if r.get("metadatas") else [],
            (r.get("distances") or [[]])[0] if r.get("distances") else [],
        )
        for r in per_domain
    ]
    merged = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    seen: set = set()
    taken = [0] * len(columns)
    depth = max((len(c[0]) for c in columns), default=0)
    for rank in range(depth):
        for col_idx, (ids, docs, metas, dists) in enumerate(columns):
            if rank >= len(ids):
                continue
            if per_domain_limit is not None and taken[col_idx] >= per_domain_limit:
                continue
            key = _dedupe_key(ids[rank], metas[rank] if rank < len(metas) else {})
            if key in seen:
                continue
            seen.add(key)
            taken[col_idx] += 1
            merged["ids"][0].append(ids[rank])
            merged["documents"][0].append(docs[rank])
            merged["metadatas"][0].append(metas[rank] if rank < len(metas) else {})
            merged["distances"][0].append(dists[rank] if rank < len(dists) else 0.0)
            if len(merged["ids"][0]) >= limit:
                return merged
    return merged


# ---------------------------------------------------------------------------
# 3. 분야별 검토 (전문가)
# ---------------------------------------------------------------------------

_EXPERT_SYSTEM_PROMPT = """\
당신은 이지스엔터프라이즈 법무팀의 **{label} 분야 검토 담당**입니다.
같은 질문을 다른 분야 담당자도 동시에 검토하므로, 당신은 오직 **{label} 관점({focus})**에서만 판단하십시오.
다른 분야의 쟁점은 언급하지 마십시오.

규칙:
- 제공된 참고 자료에 근거하고, 인용할 때 [1], [2] 같은 참고 자료 번호를 붙이십시오.
- 법령은 정식 명칭과 조문 번호로 쓰고(예: 개인정보 보호법 제25조), 확실하지 않은 조문은 쓰지 마십시오.
- 이 분야에서 판단할 쟁점이 없으면 verdict를 "해당 쟁점 없음"으로 하십시오.

반드시 아래 JSON 객체 하나만 출력하십시오 (코드 블록·설명 금지):
{{
  "verdict": "이 분야 관점의 한 줄 판단 (12자 이내, 예: 조건부 가능 / 불가 / 가능 / 추가 확인 필요)",
  "risk": "high | medium | low",
  "conclusion": "이 분야 관점의 결론 1~2문장",
  "key_points": ["핵심 근거 또는 요건 (최대 3개, 각 1문장)"],
  "cautions": ["이 분야에서 특히 주의할 점 (최대 2개)"],
  "citations": ["인용한 법령 조문 (예: 개인정보 보호법 제25조)"]
}}
"""


def _as_str_list(value, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out = [str(v).strip() for v in value if str(v).strip()]
    return out[:limit]


def parse_expert_opinion(raw: str) -> dict | None:
    """전문가 LLM 출력(JSON)을 정제한다. 형식이 깨지면 None."""
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    conclusion = str(data.get("conclusion") or "").strip()
    if not conclusion:
        return None
    risk = str(data.get("risk") or "").strip().lower()
    return {
        "verdict": str(data.get("verdict") or "").strip()[:20] or "검토 의견",
        "risk": risk if risk in _VALID_RISKS else "medium",
        "conclusion": conclusion,
        "key_points": _as_str_list(data.get("key_points"), 3),
        "cautions": _as_str_list(data.get("cautions"), 2),
        "citations": _as_str_list(data.get("citations"), 6),
    }


async def _run_expert(domain, question: str, context: str, cfg: PerspectiveConfig) -> dict | None:
    label = cfg.labels[domain]
    try:
        raw = await asyncio.wait_for(
            get_llm_client().generate(
                system_prompt=_EXPERT_SYSTEM_PROMPT.format(label=label, focus=cfg.focus.get(domain, label)),
                messages=[{"role": "user", "content": f"{context}\n\n질문: {question}"}],
                max_tokens=_EXPERT_MAX_TOKENS,
            ),
            timeout=_EXPERT_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # TimeoutError 포함 — 한 분야 실패가 전체를 막지 않게
        logger.warning("분야별 검토 실패", domain=label, error=repr(exc))
        return None

    opinion = parse_expert_opinion(raw)
    if opinion is None:
        logger.warning("분야별 검토 형식 오류", domain=label, raw=raw[:200])
        return None
    value = domain.value if hasattr(domain, "value") else str(domain)
    return {"domain": value, "label": label, **opinion}


async def run_experts(question: str, context: str, domains: list, cfg: PerspectiveConfig) -> list[dict]:
    """분야별 검토를 병렬 실행한다. 실패한 분야는 제외하고 분야 순서를 유지한다."""
    results = await asyncio.gather(*[_run_expert(d, question, context, cfg) for d in domains])
    opinions = [r for r in results if r]
    logger.info("분야별 검토 완료", requested=len(domains), succeeded=len(opinions))
    return opinions


def opinions_text(opinions: list[dict]) -> str:
    """인용 검증용 — 전문가 의견에 등장한 법령 인용을 모은 텍스트"""
    parts = []
    for o in opinions:
        parts.extend([o["conclusion"], *o["key_points"], *o["cautions"], *o["citations"]])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 4. 종합 (조정자)
# ---------------------------------------------------------------------------

COORDINATOR_ADDENDUM = """

## 분야 간 의견 대조 (이번 질문에 적용)
이 질문은 여러 법률 분야에 걸쳐 있어, 분야별 검토 담당자의 의견이 함께 제공됩니다.
의견을 단순히 합치지 말고 **대조**하십시오.

- "### 결론"에는 모든 분야를 고려한 최종 판단을 쓰십시오. 분야 간 판단이 다르면 더 엄격한 쪽을 기준으로 하십시오.
- "### 근거" 바로 앞에 아래 두 섹션을 추가하십시오.

### 분야별 의견 대조
| 쟁점 | {columns} | 정리 |
|---|{column_seps}|---|
| ... | 각 분야 판단 | 종합 판단 |

### 충돌·주의 지점
분야 간 판단이 엇갈리거나, 한 분야에서는 문제없어 보여도 다른 분야에서 제약이 생기는 지점을 구체적으로 쓰십시오.
**한 줄 판단이 같더라도 각 분야가 전제한 사실·요건이 다르면 충돌입니다.**
(예: 한 분야는 "제3자 제공이 아니다"를 전제로 가능하다고 보고, 다른 분야는 "제3자 제공이므로 동의가 필요하다"고 보면 충돌)
충돌마다 어느 쪽 해석을 따라야 안전한지와 그 이유를 쓰십시오.
전제와 요건까지 모두 같을 때만 "분야 간 판단이 일치합니다."라고 쓰고, 함께 지켜야 할 요건을 정리하십시오.
"""


def coordinator_prompt(base_prompt: str, opinions: list[dict]) -> str:
    labels = [o["label"] for o in opinions]
    return base_prompt + COORDINATOR_ADDENDUM.format(
        columns=" | ".join(f"{label} 관점" for label in labels),
        column_seps="|".join("---" for _ in labels),
    )


def coordinator_user_message(original_content: str, opinions: list[dict]) -> str:
    """기존 사용자 메시지(참고 자료 + 질문) 앞에 분야별 검토 의견을 덧붙인다."""
    blocks = []
    for o in opinions:
        points = "\n".join(f"  - {p}" for p in o["key_points"]) or "  - (없음)"
        cautions = "\n".join(f"  - {c}" for c in o["cautions"]) or "  - (없음)"
        blocks.append(
            f"### {o['label']} 검토 의견\n"
            f"- 판단: {o['verdict']} (위험도 {o['risk']})\n"
            f"- 결론: {o['conclusion']}\n"
            f"- 핵심 근거:\n{points}\n"
            f"- 주의점:\n{cautions}"
        )
    return "## 분야별 검토 의견\n" + "\n\n".join(blocks) + "\n\n" + original_content


def make_domain_classification(classification, domain):
    """특정 분야만 검색하도록 분류 결과를 복사한다 (관련 분야 제거)."""
    return classification.model_copy(update={"category": domain, "related_categories": []})

