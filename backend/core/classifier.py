"""질의 분류 + 고위험 키워드 감지 모듈"""

from pydantic import BaseModel

from core.keyword_classifier import KeywordClassifier
from models.chat import LegalCategory


# === 고위험 키워드 목록 ===

HIGH_RISK_KEYWORDS: list[str] = [
    "소송", "고소", "고발", "형사", "과태료", "벌금", "압수수색",
    "손해배상", "가처분", "가압류", "강제집행",
    "개인정보보호위원회 조사", "시정명령", "과징금",
]


# === 분야별 키워드 ===

CATEGORY_KEYWORDS: dict[LegalCategory, list[str]] = {
    LegalCategory.PRIVACY: [
        "개인정보", "처리방침", "동의서", "정보통신망", "위탁", "영향평가",
        "개인정보보호법", "정보통신망법", "처리위탁", "제3자 제공", "파기",
        "수집", "이용목적", "동의 철회", "열람 청구", "GDPR", "가명정보",
    ],
    LegalCategory.CONTRACT: [
        "계약", "NDA", "SLA", "라이선스", "납품", "하도급", "위약금",
        "계약서", "용역", "도급", "임대차", "보증금", "해지", "해제",
        "손해배상 예정액", "기밀유지", "비밀유지", "서비스 수준",
    ],
    LegalCategory.HOUSING: [
        "아파트", "관리규약", "장기수선", "관리사무소", "입주민", "공동주택",
        "관리비", "주택법", "공동주택관리법", "입주자대표회의", "관리주체",
        "장기수선충당금", "하자보수", "집합건물", "관리단", "구분소유",
    ],
    LegalCategory.LITIGATION: [
        "소송", "고소", "고발", "가처분", "가압류", "내용증명", "분쟁",
        "재판", "법원", "판결", "조정", "중재", "강제집행", "항소",
        "상고", "민사소송", "형사소송", "행정소송",
    ],
}


# === 분류 결과 스키마 ===

class ClassificationResult(BaseModel):
    category: LegalCategory
    is_high_risk: bool
    detected_keywords: list[str]
    requires_escalation: bool


# === 분류기 인스턴스 ===

_classifier = KeywordClassifier(
    category_keywords=CATEGORY_KEYWORDS,
    high_risk_keywords=HIGH_RISK_KEYWORDS,
    default_category=LegalCategory.CONTRACT,
    escalation_categories=[LegalCategory.LITIGATION],
    case_sensitive=True,
    domain_name="법률",
)


# === 공개 API (기존 호환) ===

def classify_query(query: str) -> LegalCategory:
    """키워드 매칭 기반 법률 분야 분류"""
    return _classifier.classify(query)


def detect_high_risk(query: str) -> tuple[bool, list[str]]:
    """고위험 키워드 감지"""
    return _classifier.detect_high_risk(query)


def analyze_query(query: str) -> ClassificationResult:
    """질의 분석 — 분류 + 고위험 감지 결합"""
    raw = _classifier.analyze(query)
    return ClassificationResult(**raw)
