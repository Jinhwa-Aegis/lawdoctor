"""계약 유형별 필수 점검표

계약서 리뷰 시 유형별 점검 항목을 프롬프트에 주입하여,
AI가 각 항목의 충족/리스크/누락 여부를 빠짐없이 판정하도록 한다.
근거 법령은 확실한 조문만 기재하며, 모호한 경우 법령명만 적는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from config import settings
from core.llm import get_llm_client

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    name: str          # 점검 항목명
    guide: str         # 무엇을 확인해야 하는지
    legal_basis: str = ""  # 근거 법령 (확실한 경우만)


@dataclass(frozen=True)
class ContractType:
    key: str
    label: str
    description: str
    items: list[ChecklistItem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 공통 점검 항목 (모든 유형에 추가)
# ---------------------------------------------------------------------------

_COMMON_ITEMS: list[ChecklistItem] = [
    ChecklistItem("parties", "당사자 및 지위", "계약 당사자, 대표자·권한, 이지스엔터프라이즈가 갑/을 중 어느 쪽인지"),
    ChecklistItem("term", "계약 기간·갱신", "시작·종료일, 자동 갱신 여부와 갱신 거절 통지 기한"),
    ChecklistItem("termination", "해지 사유·정산", "해지 사유의 균형, 최고(催告) 기간, 해지 시 대금·자료 정산"),
    ChecklistItem("liability", "손해배상·책임 제한", "배상 범위, 상한, 간접손해 배제가 일방에게만 유리한지",
                  "민법 제393조, 민법 제398조"),
    ChecklistItem("dispute", "분쟁 해결·관할", "관할 법원(상대방 소재지 전속관할 여부), 중재 조항, 준거법"),
]

# ---------------------------------------------------------------------------
# 유형별 점검 항목
# ---------------------------------------------------------------------------

CONTRACT_TYPES: dict[str, ContractType] = {
    "nda": ContractType(
        key="nda",
        label="비밀유지계약(NDA)",
        description="협업·투자·영업 검토 전 정보 교환",
        items=[
            ChecklistItem("nda_definition", "비밀정보의 정의·범위", "당사가 정보 수령자라면 '비밀' 표시 없는 모든 정보까지 포함하는 포괄적 정의는 불리함(risk). 당사가 제공자라면 범위가 좁아 보호가 안 되는지 확인"),
            ChecklistItem("nda_exceptions", "비밀유지 예외", "공지 정보, 기보유 정보, 제3자로부터 적법 취득, 독자 개발, 법령상 공개 의무"),
            ChecklistItem("nda_purpose", "사용 목적 제한", "정해진 목적 외 사용 금지가 명확한지"),
            ChecklistItem("nda_duration", "비밀유지 기간·존속", "계약 종료 후 존속 기간이 합리적인지 (무기한 여부)"),
            ChecklistItem("nda_return", "반환·파기 의무", "종료 시 반환·파기 및 확인서 제출 절차"),
            ChecklistItem("nda_penalty", "위약벌·손해배상 예정액", "위약벌이 과도한지, 손해배상액 예정과 구분되는지", "민법 제398조"),
            ChecklistItem("nda_mutual", "의무의 상호성", "당사만 의무를 지는 일방 계약인데 당사도 정보를 제공하거나 의무가 과중하면 risk"),
            ChecklistItem("nda_personal_info", "개인정보 포함 여부", "교환 정보에 개인정보가 포함되면 제공 근거와 보호조치", "개인정보 보호법 제17조"),
        ],
    ),
    "service": ContractType(
        key="service",
        label="용역·SI·외주 개발",
        description="개발·구축·컨설팅 등 업무 위탁 및 수행",
        items=[
            ChecklistItem("svc_scope", "업무 범위·산출물", "과업 범위(SOW)와 산출물 목록이 구체적인지, 추가 과업 처리 방식"),
            ChecklistItem("svc_payment", "대금·지급 조건", "지급 시기·방법, 선급금·중도금, 지연이자"),
            ChecklistItem("svc_acceptance", "검수 기준·절차", "검수 기준, 기간, 기간 경과 시 간주검수 조항"),
            ChecklistItem("svc_warranty", "하자담보 책임", "하자보수 범위와 기간이 합리적인지", "민법 제667조"),
            ChecklistItem("svc_ip", "지식재산권 귀속", "산출물 권리 귀속, 기존 보유 IP·오픈소스 처리, 2차 활용 범위"),
            ChecklistItem("svc_delay", "지체상금", "지체상금률과 상한이 있는지 (상한 없는 지체상금은 과도할 수 있음)"),
            ChecklistItem("svc_change", "계약 변경 절차", "범위·일정 변경 시 서면 합의 및 대금 조정"),
            ChecklistItem("svc_subcontract", "재위탁(하도급) 제한", "재위탁 시 사전 동의, 하도급법 적용 여부", "하도급거래 공정화에 관한 법률"),
            ChecklistItem("svc_privacy", "개인정보 처리위탁", "수행 중 개인정보를 처리하면 위탁계약 필수 기재사항 포함 여부", "개인정보 보호법 제26조"),
        ],
    ),
    "saas": ContractType(
        key="saas",
        label="SaaS·소프트웨어 공급/라이선스",
        description="클라우드 서비스 이용, 솔루션 공급, 라이선스",
        items=[
            ChecklistItem("saas_license", "라이선스 범위", "사용자 수, 기간, 지역, 양도·재허락 금지 범위"),
            ChecklistItem("saas_sla", "서비스 수준(SLA)", "가용률, 장애 대응 시간, 미달 시 보상(크레딧)"),
            ChecklistItem("saas_data", "데이터 소유권·반환·삭제", "고객 데이터 소유권, 종료 시 반환 형식·기한, 삭제 확인"),
            ChecklistItem("saas_privacy", "개인정보 처리위탁", "위탁 필수 기재사항, 재위탁 동의", "개인정보 보호법 제26조"),
            ChecklistItem("saas_overseas", "개인정보 국외 이전", "해외 서버·재수탁자 이용 시 이전 근거와 고지", "개인정보 보호법 제28조의8"),
            ChecklistItem("saas_security", "보안 의무·사고 통지", "보안 조치 수준, 침해사고 통지 기한"),
            ChecklistItem("saas_maintenance", "유지보수·업데이트", "포함 범위, 버전 지원 종료 정책"),
            ChecklistItem("saas_fee", "요금·인상 조건", "요금 인상 통지·상한, 자동 갱신 시 가격"),
            ChecklistItem("saas_ip_indemnity", "지식재산권 침해 면책", "제3자 IP 침해 주장 시 공급자 방어·배상 의무"),
            ChecklistItem("saas_unfair_terms", "약관의 불공정성", "일방적 면책·변경권 등 약관규제법상 무효 가능 조항", "약관의 규제에 관한 법률 제7조"),
        ],
    ),
    "privacy_outsourcing": ContractType(
        key="privacy_outsourcing",
        label="개인정보 처리위탁",
        description="콜센터·발송·호스팅 등 개인정보 처리 업무 위탁",
        items=[
            ChecklistItem("po_purpose_limit", "목적 외 처리 금지", "위탁업무 수행 목적 외 개인정보 처리 금지 명시", "개인정보 보호법 제26조"),
            ChecklistItem("po_safeguards", "기술적·관리적 보호조치", "접근 통제, 암호화, 접속기록 보관 등 안전성 확보조치", "개인정보 보호법 제29조"),
            ChecklistItem("po_scope", "위탁업무의 목적·범위", "위탁하는 업무 내용과 처리 개인정보 항목이 구체적인지"),
            ChecklistItem("po_resubcontract", "재위탁 제한", "재위탁 금지 또는 위탁자 사전 동의 요건"),
            ChecklistItem("po_supervision", "관리·감독", "처리 현황 점검, 교육, 감독 권한", "개인정보 보호법 제26조"),
            ChecklistItem("po_liability", "위반 시 손해배상 책임", "수탁자 의무 위반 시 손해배상 등 책임 소재"),
            ChecklistItem("po_disclosure", "위탁 사실 공개", "위탁 업무 내용과 수탁자를 처리방침 등에 공개할 수 있는지", "개인정보 보호법 제26조"),
            ChecklistItem("po_destruction", "종료 시 반환·파기", "계약 종료 시 개인정보 반환·파기 및 확인 절차", "개인정보 보호법 제21조"),
        ],
    ),
    "housing_management": ContractType(
        key="housing_management",
        label="공동주택 관리·용역",
        description="주택관리업자 위탁관리, 경비·청소·승강기 등 용역",
        items=[
            ChecklistItem("hm_selection", "사업자 선정 절차", "입주자대표회의 의결, 경쟁입찰 등 선정 지침 준수 여부",
                          "공동주택관리법 제7조, 공동주택관리법 제25조"),
            ChecklistItem("hm_scope", "업무 범위·관리비 구분", "위탁 업무 범위, 관리비·사용료 항목 구분"),
            ChecklistItem("hm_fee", "수수료·용역비 산정", "산정 기준, 인건비 변동 시 조정 방식"),
            ChecklistItem("hm_staffing", "인력 배치·근로관계", "배치 인원 기준, 근로자 고용 승계, 최저임금 반영"),
            ChecklistItem("hm_insurance", "보험·보증", "배상책임보험, 이행보증 가입 여부"),
            ChecklistItem("hm_cctv_privacy", "입주민 개인정보·영상정보", "입주민 정보·CCTV 영상 처리 위탁 및 보호조치",
                          "개인정보 보호법 제25조, 개인정보 보호법 제26조"),
            ChecklistItem("hm_subcontract", "재하도급 금지", "재위탁·재하도급 제한"),
            ChecklistItem("hm_early_termination", "중도 해지·정산", "입주자대표회의 의결에 따른 해지 및 정산"),
        ],
    ),
    "lease": ContractType(
        key="lease",
        label="부동산 임대차(사무실·상가)",
        description="사무실·상가 임차",
        items=[
            ChecklistItem("lease_deposit", "보증금·차임·인상", "차임 증액 제한 준수 여부 (환산보증금 기준 적용 대상 확인)", "상가건물 임대차보호법 제11조"),
            ChecklistItem("lease_renewal", "기간·갱신요구권", "계약갱신요구권 행사 가능 기간 보장", "상가건물 임대차보호법 제10조"),
            ChecklistItem("lease_restoration", "원상복구 범위", "인테리어·시설물 원상복구 범위가 과도한지"),
            ChecklistItem("lease_maintenance", "수선 의무 분담", "임대인 수선 의무를 임차인에게 전가하는지", "민법 제623조"),
            ChecklistItem("lease_management_fee", "관리비 항목", "관리비 항목·정산 방식의 명확성"),
            ChecklistItem("lease_sublease", "전대·양도 제한", "전대·양도 시 동의 요건", "민법 제629조"),
            ChecklistItem("lease_premium", "권리금 회수 기회", "권리금 회수 방해 금지 관련 특약", "상가건물 임대차보호법 제10조의4"),
            ChecklistItem("lease_opposability", "대항력·우선변제", "사업자등록·확정일자 등 대항력 확보", "상가건물 임대차보호법 제3조"),
        ],
    ),
    "general": ContractType(
        key="general",
        label="기타 일반 계약",
        description="위 유형에 해당하지 않는 계약",
        items=[
            ChecklistItem("gen_purpose", "계약 목적·대상", "계약 목적과 대상이 명확한지"),
            ChecklistItem("gen_consideration", "대가·지급 조건", "금액, 지급 시기·방법"),
            ChecklistItem("gen_confidentiality", "비밀유지", "비밀유지 의무 및 존속 기간"),
            ChecklistItem("gen_assignment", "권리·의무 양도 제한", "상대방 동의 없는 양도 금지"),
        ],
    ),
}

AUTO_DETECT = "auto"


def get_checklist(type_key: str) -> list[ChecklistItem]:
    """유형별 점검 항목 + 공통 점검 항목"""
    ct = CONTRACT_TYPES.get(type_key, CONTRACT_TYPES["general"])
    return [*ct.items, *_COMMON_ITEMS]


def list_contract_types() -> list[dict]:
    """프론트엔드 유형 선택용 목록"""
    return [
        {"key": ct.key, "label": ct.label, "description": ct.description,
         "item_count": len(ct.items) + len(_COMMON_ITEMS)}
        for ct in CONTRACT_TYPES.values()
    ]


def format_checklist_prompt(type_key: str) -> str:
    """점검표를 LLM 프롬프트용 텍스트로 변환"""
    ct = CONTRACT_TYPES.get(type_key, CONTRACT_TYPES["general"])
    lines = [f"## 계약 유형: {ct.label}", "## 필수 점검 항목 (모든 항목에 대해 checklist_results를 작성할 것)"]
    for item in get_checklist(type_key):
        basis = f" (근거: {item.legal_basis})" if item.legal_basis else ""
        lines.append(f"- [{item.id}] {item.name}: {item.guide}{basis}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 유형 자동 감지
# ---------------------------------------------------------------------------

_DETECT_PROMPT = """\
아래 계약서 앞부분을 읽고 계약 유형을 다음 키 중 하나로만 답하십시오.
{options}
키 하나만 출력하고 다른 말은 하지 마십시오."""


def parse_detected_type(raw: str) -> str:
    """LLM 출력에서 유형 키를 추출한다. 실패 시 general."""
    text = (raw or "").strip().lower()
    for key in CONTRACT_TYPES:
        if re.search(rf"(?<![a-z_]){re.escape(key)}(?![a-z_])", text):
            return key
    return "general"


async def detect_contract_type(text: str) -> str:
    """경량 모델로 계약 유형을 판별한다."""
    options = "\n".join(f"- {ct.key}: {ct.label} ({ct.description})" for ct in CONTRACT_TYPES.values())
    try:
        raw = await get_llm_client().generate(
            system_prompt=_DETECT_PROMPT.format(options=options),
            messages=[{"role": "user", "content": text[:4000]}],
            max_tokens=20,
            model=settings.query_rewrite_model,
        )
        detected = parse_detected_type(raw)
    except Exception as exc:
        logger.warning("계약 유형 자동 감지 실패", error=str(exc))
        detected = "general"
    logger.info("계약 유형 감지", contract_type=detected)
    return detected
