"""제네릭 키워드 기반 질의 분류기

법률·보안 등 도메인별 분류기가 공유하는 핵심 로직을 캡슐화한다.
각 도메인 모듈(classifier.py, security_classifier.py)은 이 클래스의 인스턴스를
생성하여 키워드 목록과 설정만 주입하면 된다.
"""

from enum import Enum

import structlog

logger = structlog.get_logger()


class KeywordClassifier:
    """키워드 매칭 기반 질의 분류기

    Parameters
    ----------
    category_keywords : dict[Enum, list[str]]
        분야(Enum) → 키워드 목록 매핑.
    high_risk_keywords : list[str]
        고위험으로 간주할 키워드 목록.
    default_category : Enum
        매칭되는 키워드가 없을 때 반환할 기본 분야.
    escalation_categories : list[Enum] | None
        해당 분야로 분류되면 에스컬레이션이 필요한 분야 목록.
    case_sensitive : bool
        True이면 대소문자를 구분하여 매칭한다. 기본값 True.
    domain_name : str
        로그 메시지에 사용할 도메인 이름(예: "법률", "보안").
    """

    def __init__(
        self,
        category_keywords: dict[Enum, list[str]],
        high_risk_keywords: list[str],
        default_category: Enum,
        escalation_categories: list[Enum] | None = None,
        case_sensitive: bool = True,
        domain_name: str = "general",
    ):
        self.category_keywords = category_keywords
        self.high_risk_keywords = high_risk_keywords
        self.default_category = default_category
        self.escalation_categories = escalation_categories or []
        self.case_sensitive = case_sensitive
        self.domain_name = domain_name

    def _match(self, keyword: str, text: str) -> bool:
        """키워드가 텍스트에 포함되어 있는지 확인"""
        if self.case_sensitive:
            return keyword in text
        return keyword.lower() in text.lower()

    def score(self, query: str) -> dict[Enum, int]:
        """분야별 키워드 매칭 횟수"""
        scores: dict[Enum, int] = {cat: 0 for cat in self.category_keywords}
        for category, keywords in self.category_keywords.items():
            for keyword in keywords:
                if self._match(keyword, query):
                    scores[category] += 1
        return scores

    def classify(self, query: str) -> Enum:
        """키워드 매칭 기반 분야 분류

        각 분야별 키워드 매칭 횟수를 합산하여 가장 높은 점수의 분야를 반환한다.
        매칭되는 키워드가 하나도 없으면 default_category를 반환한다.
        """
        scores = self.score(query)
        max_category = max(scores, key=lambda k: scores[k])
        if scores[max_category] == 0:
            return self.default_category

        return max_category

    def detect_high_risk(self, query: str) -> tuple[bool, list[str]]:
        """고위험 키워드 감지

        Returns
        -------
        tuple[bool, list[str]]
            (고위험 여부, 감지된 키워드 목록)
        """
        detected = [kw for kw in self.high_risk_keywords if self._match(kw, query)]
        return (len(detected) > 0, detected)

    def analyze(self, query: str) -> dict:
        """질의 분석 — 분류 + 고위험 감지 결합

        Returns
        -------
        dict
            category(Enum), is_high_risk(bool),
            detected_keywords(list[str]), requires_escalation(bool)를 담은 딕셔너리.
            도메인별 모듈이 이 결과를 자신의 Pydantic 결과 모델로 변환한다.
        """
        category = self.classify(query)
        # 주 분야 외에 키워드가 하나라도 걸린 분야 — 복합 질의의 검색 범위 확장에 사용
        related_categories = [
            cat for cat, sc in sorted(self.score(query).items(), key=lambda kv: -kv[1])
            if sc > 0 and cat != category
        ]
        is_high_risk, detected_keywords = self.detect_high_risk(query)
        requires_escalation = is_high_risk or category in self.escalation_categories

        logger.info(
            f"{self.domain_name} 질의 분석 결과",
            category=category.value,
            related_categories=[c.value for c in related_categories],
            is_high_risk=is_high_risk,
            detected_keywords=detected_keywords,
            requires_escalation=requires_escalation,
        )

        return {
            "category": category,
            "related_categories": related_categories,
            "is_high_risk": is_high_risk,
            "detected_keywords": detected_keywords,
            "requires_escalation": requires_escalation,
        }
