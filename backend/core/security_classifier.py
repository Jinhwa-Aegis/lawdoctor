"""보안 질의 분류 + 고위험 키워드 감지 모듈"""

from pydantic import BaseModel

from core.keyword_classifier import KeywordClassifier
from models.chat import SecurityCategory


# === 고위험 키워드 목록 ===

SECURITY_HIGH_RISK_KEYWORDS: list[str] = [
    "침해사고", "랜섬웨어", "해킹", "데이터 유출", "정보유출",
    "악성코드", "APT", "제로데이", "DDoS", "피싱",
    "내부자 위협", "권한 탈취", "백도어", "루트킷",
    "개인정보 유출", "크리덴셜 탈취",
]


# === 분야별 키워드 ===

SECURITY_CATEGORY_KEYWORDS: dict[SecurityCategory, list[str]] = {
    SecurityCategory.NETWORK: [
        "방화벽", "firewall", "IDS", "IPS", "VPN", "네트워크",
        "세그먼테이션", "DDoS", "포트", "프로토콜", "패킷",
        "NAC", "SSL", "TLS", "DNS", "프록시", "WAF",
    ],
    SecurityCategory.SYSTEM: [
        "서버", "OS", "운영체제", "패치", "업데이트", "로그",
        "접근제어", "계정관리", "권한관리", "엔드포인트",
        "백신", "안티바이러스", "EDR", "SIEM",
    ],
    SecurityCategory.APPLICATION: [
        "시큐어코딩", "OWASP", "XSS", "SQL 인젝션", "인젝션",
        "웹 취약점", "API 보안", "인증", "세션", "CSRF",
        "소스코드", "코드 리뷰", "취약점 점검", "모의해킹",
    ],
    SecurityCategory.CLOUD: [
        "클라우드", "AWS", "Azure", "GCP", "IAM",
        "컨테이너", "쿠버네티스", "도커", "SaaS", "IaaS",
        "CSPM", "CWPP", "클라우드 보안",
    ],
    SecurityCategory.COMPLIANCE: [
        "ISMS", "ISMS-P", "인증", "컴플라이언스", "규정",
        "개인정보보호법", "정보통신망법", "전자금융", "감독규정",
        "ISO 27001", "SOC 2", "GDPR", "NIST",
        "정보보호", "관리체계",
    ],
    SecurityCategory.DATA_PROTECTION: [
        "암호화", "DLP", "데이터 보호", "백업", "복구",
        "데이터 분류", "접근통제", "마스킹", "토큰화",
        "키 관리", "인증서", "PKI",
    ],
    SecurityCategory.INCIDENT: [
        "침해사고", "사고대응", "포렌식", "IR", "BCP",
        "재해복구", "DR", "랜섬웨어", "악성코드",
        "사고 분석", "침해 지표", "IOC",
    ],
    SecurityCategory.AUDIT: [
        "감사", "점검", "진단", "모의해킹", "침투테스트",
        "취약점 스캔", "보안 진단", "체크리스트",
        "CVE", "보안 평가",
    ],
}


# === 분류 결과 스키마 ===

class SecurityClassificationResult(BaseModel):
    category: SecurityCategory
    is_high_risk: bool
    detected_keywords: list[str]
    requires_escalation: bool


# === 분류기 인스턴스 ===

_classifier = KeywordClassifier(
    category_keywords=SECURITY_CATEGORY_KEYWORDS,
    high_risk_keywords=SECURITY_HIGH_RISK_KEYWORDS,
    default_category=SecurityCategory.COMPLIANCE,
    escalation_categories=[SecurityCategory.INCIDENT],
    case_sensitive=False,
    domain_name="보안",
)


# === 공개 API (기존 호환) ===

def classify_security_query(query: str) -> SecurityCategory:
    """키워드 매칭 기반 보안 분야 분류"""
    return _classifier.classify(query)


def detect_security_high_risk(query: str) -> tuple[bool, list[str]]:
    """보안 고위험 키워드 감지"""
    return _classifier.detect_high_risk(query)


def analyze_security_query(query: str) -> SecurityClassificationResult:
    """보안 질의 분석 — 분류 + 고위험 감지 결합"""
    raw = _classifier.analyze(query)
    return SecurityClassificationResult(**raw)
