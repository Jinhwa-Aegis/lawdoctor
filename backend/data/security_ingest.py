"""
보안 가이드 문서 수집 및 벡터 DB 적재 모듈

security_guides, security_incidents 컬렉션에 보안 자료를 적재한다.
- PDF 파일 적재: 보안 가이드/사례 PDF를 파싱하여 적재
- 내장 지식베이스: ISMS-P, OWASP Top 10, KISA 가이드 등 핵심 보안 기준 내장
"""

import structlog
from pathlib import Path

from core.embeddings import embed_batch
from data.vector_store import get_vector_store
from data.ingest import chunk_text, extract_text

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# PDF 기반 보안 가이드 적재
# ---------------------------------------------------------------------------

async def ingest_security_pdf(
    filepath: str,
    guide_name: str = "",
    standard: str = "",
    section: str = "",
    collection: str = "security_guides",
) -> int:
    """
    보안 문서 파일(PDF, DOCX, HWP)을 파싱하고 벡터 DB에 적재

    Args:
        filepath: 문서 파일 경로 (.pdf, .docx, .hwp)
        guide_name: 가이드 이름 (예: "ISMS-P 인증기준 해설서")
        standard: 관련 표준 (예: "ISMS-P", "ISO 27001")
        section: 섹션 (예: "2.6 접근통제")
        collection: 적재할 컬렉션 ("security_guides" 또는 "security_incidents")

    Returns:
        적재된 청크 수
    """
    logger.info(
        "보안 문서 적재 시작",
        filepath=filepath,
        guide_name=guide_name,
        standard=standard,
        collection=collection,
    )

    try:
        text = extract_text(filepath)

        if not text.strip():
            logger.warning("빈 PDF", filepath=filepath)
            return 0

        from core.semantic_chunker import semantic_chunk_text
        chunks = semantic_chunk_text(text, doc_type="consultation", max_chunk_size=800)

        if not chunks:
            logger.warning("청크 생성 실패", filepath=filepath)
            return 0

        file_path = Path(filepath)
        resolved_guide_name = guide_name or file_path.stem

        for chunk in chunks:
            chunk["metadata"].update({
                "source": file_path.name,
                "source_type": "security_guide" if collection == "security_guides" else "security_incident",
                "guide_name": resolved_guide_name,
                "standard": standard,
                "section": section,
                "filepath": str(file_path.absolute()),
            })

        texts = [chunk["text"] for chunk in chunks]
        embeddings = await embed_batch(texts)

        ids = [
            f"sec_{file_path.stem}_chunk_{chunk['metadata']['chunk_index']}"
            for chunk in chunks
        ]
        metadatas = [chunk["metadata"] for chunk in chunks]

        vector_store = get_vector_store()
        vector_store.upsert_and_cleanup(
            collection_name=collection,
            id_prefix=f"sec_{file_path.stem}_chunk_",
            documents=texts,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

        logger.info(
            "보안 PDF 적재 완료",
            filepath=filepath,
            collection=collection,
            chunks=len(chunks),
        )
        return len(chunks)

    except Exception as e:
        logger.error(
            "보안 PDF 적재 실패",
            filepath=filepath,
            error=str(e),
            exc_info=True,
        )
        raise


async def ingest_security_directory(
    dir_path: str,
    standard: str = "",
    collection: str = "security_guides",
) -> dict[str, int]:
    """
    디렉토리 내 모든 보안 PDF 파일 적재

    Args:
        dir_path: 디렉토리 경로
        standard: 관련 표준 (모든 파일에 공통 적용)
        collection: 적재할 컬렉션

    Returns:
        파일별 적재된 청크 수
    """
    logger.info("보안 디렉토리 적재 시작", dir_path=dir_path, collection=collection)

    directory = Path(dir_path)

    if not directory.exists():
        logger.error("디렉토리 없음", dir_path=dir_path)
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {dir_path}")

    pdf_files = list(directory.glob("**/*.pdf"))
    logger.info("보안 PDF 파일 발견", count=len(pdf_files))

    results = {}
    total_chunks = 0

    for pdf_file in pdf_files:
        try:
            chunk_count = await ingest_security_pdf(
                filepath=str(pdf_file),
                guide_name=pdf_file.stem,
                standard=standard,
                collection=collection,
            )
            results[pdf_file.name] = chunk_count
            total_chunks += chunk_count

        except Exception as e:
            logger.error(
                "파일 적재 실패",
                filepath=str(pdf_file),
                error=str(e),
            )
            results[pdf_file.name] = 0

    logger.info(
        "보안 디렉토리 적재 완료",
        dir_path=dir_path,
        files=len(results),
        total_chunks=total_chunks,
    )
    return results


# ---------------------------------------------------------------------------
# 내장 보안 지식베이스
# ---------------------------------------------------------------------------

BUILTIN_SECURITY_GUIDES: list[dict] = [
    # --- ISMS-P 인증기준 ---
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "1.1 정보보호 정책 수립",
        "text": (
            "ISMS-P 1.1 정보보호 정책 수립: "
            "조직의 정보보호 및 개인정보보호 정책을 수립하고, 경영진의 승인을 받아 "
            "내·외부 이해관계자에게 전달해야 한다. "
            "정보보호 정책에는 정보보호 목적, 범위, 책임, 위반 시 제재 사항을 포함해야 하며, "
            "관련 법규 및 계약 사항을 반영해야 한다. "
            "정책은 정기적으로(최소 연 1회) 검토하여 환경 변화에 따라 개정해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "1.2 정보보호 조직 구성",
        "text": (
            "ISMS-P 1.2 정보보호 조직 구성: "
            "정보보호 최고책임자(CISO)를 지정하고, 정보보호 업무를 수행할 전담 조직을 구성해야 한다. "
            "정보보호위원회를 구성하여 정보보호 정책, 대책, 예산 등 주요 사항을 심의·의결한다. "
            "정보통신망법 제45조의3에 따라 자산총액, 매출액 등이 일정 기준 이상인 사업자는 "
            "CISO를 의무적으로 지정해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "1.3 정보자산 관리",
        "text": (
            "ISMS-P 1.3 정보자산 관리: "
            "조직의 업무 수행에 필요한 정보자산(서버, 네트워크, DB, 문서, 소프트웨어 등)을 "
            "식별하고 목록을 관리해야 한다. 자산별 중요도를 평가하여 보호등급을 부여하고, "
            "자산 책임자를 지정해야 한다. 자산 목록은 변경 시 갱신하며, "
            "최소 연 1회 정기점검을 수행해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "1.4 위험 관리",
        "text": (
            "ISMS-P 1.4 위험 관리: "
            "정보자산에 대한 위험을 식별·분석·평가하는 체계적인 위험관리 프로세스를 수립해야 한다. "
            "위험평가는 최소 연 1회 정기적으로 수행하며, 중대한 환경 변화(신규 시스템 도입, "
            "조직 변경, 보안사고 발생 등) 시에는 수시로 수행한다. "
            "위험처리 계획을 수립하여 잔여위험을 경영진이 수용 가능한 수준으로 관리해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.1 인적 보안",
        "text": (
            "ISMS-P 2.1 인적 보안: "
            "임직원 및 외부 인력에 대한 정보보호 서약 및 보안 교육을 실시해야 한다. "
            "채용 시 보안 서약서를 징구하고, 연 1회 이상 정보보호 인식 교육을 실시한다. "
            "퇴직 시 자산 반납, 접근권한 회수 및 비밀유지 확약서를 징구해야 한다. "
            "외주 인력에 대해서도 동일한 수준의 보안 요건을 적용해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.2 물리적 보안",
        "text": (
            "ISMS-P 2.2 물리적 보안: "
            "서버실, 전산실 등 정보처리시설에 대해 출입 통제를 실시하고 "
            "출입 기록을 유지해야 한다. 보호구역을 제한구역, 통제구역, 접견구역으로 "
            "등급을 나누어 관리하며, CCTV 등 물리적 감시 체계를 운영한다. "
            "자연재해, 화재, 정전 등에 대비한 환경 보호 대책을 수립해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.5 인증 및 권한관리",
        "text": (
            "ISMS-P 2.5 인증 및 권한관리: "
            "사용자 계정은 개인별로 고유하게 발급하고, 비밀번호 복잡성 정책(8자 이상, "
            "영문+숫자+특수문자 조합)을 적용해야 한다. "
            "관리자 계정은 최소 필요 인원에게만 부여하고, 2단계 인증(MFA)을 적용한다. "
            "퇴직·이동 시 접근권한을 즉시 회수하며, 최소 분기 1회 접근권한 현행화를 수행한다. "
            "특수권한(root, admin 등)은 별도 승인 절차를 거쳐 부여해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.6 접근통제",
        "text": (
            "ISMS-P 2.6 접근통제: "
            "네트워크, 서버, 데이터베이스, 응용프로그램 등 각 계층별 접근통제 정책을 수립한다. "
            "업무 필요성에 따라 최소 권한 원칙을 적용하며, 외부에서의 접근은 VPN 등 "
            "안전한 접속 수단을 통해서만 허용한다. 접근 로그를 기록하고 정기적으로 검토한다. "
            "비인가 접근 시도를 탐지·차단하는 체계를 운영해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.7 암호화",
        "text": (
            "ISMS-P 2.7 암호화: "
            "개인정보 및 중요 정보의 전송 시 SSL/TLS 등 암호화를 적용해야 한다. "
            "비밀번호는 일방향 암호화(해시)하여 저장하며, 주민등록번호·카드번호 등 "
            "고유식별정보는 안전한 알고리즘(AES-256 등)으로 암호화하여 저장한다. "
            "암호키는 안전하게 생성·보관·폐기하며, 키 관리 절차를 수립해야 한다. "
            "개인정보 보호법 제24조의2, 제29조 및 시행령 제30조에 따른 암호화 조치가 필요하다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.9 시스템 및 서비스 보안관리",
        "text": (
            "ISMS-P 2.9 시스템 및 서비스 보안관리: "
            "운영체제, 데이터베이스, 웹서버 등에 대한 보안 설정 기준(Hardening)을 수립하고 적용한다. "
            "보안 패치는 영향도 분석 후 신속하게 적용하며, 패치 현황을 관리한다. "
            "불필요한 서비스·포트를 제거하고, 시스템 로그를 생성·보관·분석한다. "
            "백업 정책을 수립하여 정기적으로 백업하고 복원 테스트를 수행해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.10 시스템 및 서비스 운영관리",
        "text": (
            "ISMS-P 2.10 시스템 및 서비스 운영관리: "
            "변경관리 절차를 수립하여 시스템·네트워크·애플리케이션의 변경 사항을 통제한다. "
            "성능 및 용량 관리를 통해 서비스 가용성을 보장하며, "
            "장애 발생 시 복구 절차에 따라 신속하게 대응한다. "
            "운영 환경과 개발·테스트 환경을 분리하여 운영 안정성을 확보해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.11 침해사고 관리",
        "text": (
            "ISMS-P 2.11 침해사고 관리: "
            "침해사고 대응 절차를 수립하고, 사고 유형별 대응 매뉴얼을 마련해야 한다. "
            "침해사고 발생 시 탐지 → 분석 → 대응 → 복구 → 사후조치의 단계별 절차를 수행한다. "
            "정보통신망법에 따라 침해사고 발생 시 24시간 이내에 KISA에 신고해야 한다. "
            "사고 분석 결과를 기반으로 재발 방지 대책을 수립하고 이행해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "2.12 재해복구",
        "text": (
            "ISMS-P 2.12 재해복구: "
            "업무연속성 계획(BCP)과 재해복구 계획(DRP)을 수립해야 한다. "
            "핵심 업무 시스템의 RTO(목표복구시간)와 RPO(목표복구시점)를 정의하고, "
            "이를 충족하는 백업·복구 체계를 구축한다. "
            "재해복구 훈련을 최소 연 1회 실시하고 결과를 경영진에 보고해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "3.1 개인정보 수집",
        "text": (
            "ISMS-P 3.1 개인정보 수집: "
            "개인정보 보호법 제15조에 따라 개인정보 수집 시 정보주체의 동의를 받아야 한다. "
            "수집 목적에 필요한 최소한의 항목만 수집(최소수집 원칙)하며, "
            "필수항목과 선택항목을 구분하여 안내해야 한다. "
            "개인정보 처리방침에 수집 항목, 목적, 보유기간을 명시해야 한다."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "3.3 개인정보 제공",
        "text": (
            "ISMS-P 3.3 개인정보 제3자 제공: "
            "개인정보를 제3자에게 제공할 때는 정보주체의 별도 동의를 받아야 한다. "
            "제공받는 자, 제공 목적, 제공 항목, 보유기간을 동의서에 명시해야 하며, "
            "개인정보 보호법 제17조에 따라 처리한다. "
            "개인정보 처리 위탁 시에는 위탁 계약서에 보안 요건을 포함하고 "
            "수탁자에 대한 교육·감독을 실시해야 한다(개인정보 보호법 제26조)."
        ),
    },
    {
        "guide_name": "ISMS-P 인증기준",
        "standard": "ISMS-P",
        "section": "3.5 개인정보 파기",
        "text": (
            "ISMS-P 3.5 개인정보 파기: "
            "개인정보의 보유기간이 경과하거나 처리 목적이 달성된 경우 "
            "지체 없이(5일 이내) 파기해야 한다(개인정보 보호법 제21조). "
            "전자적 파일은 복원이 불가능한 방법으로 삭제하고, "
            "종이 문서는 파쇄 또는 소각한다. "
            "법령에 따라 보존이 필요한 경우 다른 개인정보와 분리하여 저장·관리해야 한다."
        ),
    },

    # --- OWASP Top 10 (2021) ---
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A01:2021 접근 제어 취약점",
        "text": (
            "OWASP A01:2021 Broken Access Control (접근 제어 취약점): "
            "인증된 사용자가 권한 없는 기능이나 데이터에 접근할 수 있는 취약점이다. "
            "주요 사례: 수평적 권한 상승(다른 사용자 데이터 접근), 수직적 권한 상승(관리자 기능 접근), "
            "IDOR(Insecure Direct Object Reference), URL 조작을 통한 비인가 접근. "
            "대응방안: 기본적으로 접근 거부 정책 적용, 서버측에서 접근 제어 검증, "
            "RBAC/ABAC 기반 권한 관리, JWT 토큰 무결성 검증, API 엔드포인트별 권한 검증."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A02:2021 암호화 실패",
        "text": (
            "OWASP A02:2021 Cryptographic Failures (암호화 실패): "
            "민감 데이터를 보호하기 위한 암호화가 누락되거나 부적절한 경우 발생하는 취약점이다. "
            "주요 사례: 평문 데이터 전송(HTTP 사용), 취약한 암호 알고리즘(MD5, SHA-1, DES), "
            "하드코딩된 암호키, 자체 서명 인증서 사용. "
            "대응방안: TLS 1.2+ 사용, AES-256/RSA-2048 이상의 강력한 알고리즘 적용, "
            "비밀번호는 bcrypt/scrypt/Argon2로 해싱, 암호키 관리 체계(HSM/KMS) 도입."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A03:2021 인젝션",
        "text": (
            "OWASP A03:2021 Injection (인젝션): "
            "사용자 입력이 적절히 검증·이스케이프되지 않아 공격자가 악의적 명령을 실행할 수 있는 취약점이다. "
            "유형: SQL 인젝션, NoSQL 인젝션, OS 명령 인젝션, LDAP 인젝션, XSS(Cross-Site Scripting). "
            "대응방안: 파라미터화된 쿼리(Prepared Statement) 사용, ORM 사용, "
            "입력값 화이트리스트 검증, 출력 인코딩, WAF(Web Application Firewall) 적용. "
            "시큐어코딩 가이드에 따라 모든 외부 입력을 신뢰하지 않는 원칙을 적용해야 한다."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A04:2021 불안전한 설계",
        "text": (
            "OWASP A04:2021 Insecure Design (불안전한 설계): "
            "설계 단계에서 보안 요구사항이 누락되어 발생하는 근본적인 취약점이다. "
            "코딩 수준의 문제가 아닌 아키텍처·설계 수준의 결함으로, 구현 후 수정이 어렵다. "
            "대응방안: 위협 모델링(Threat Modeling) 수행, 보안 설계 원칙(Secure by Design) 적용, "
            "비즈니스 로직 검증, 남용 사례(Abuse Case) 정의, "
            "SDL(Secure Development Lifecycle) 프로세스 도입."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A05:2021 보안 설정 오류",
        "text": (
            "OWASP A05:2021 Security Misconfiguration (보안 설정 오류): "
            "시스템, 프레임워크, 클라우드 서비스의 보안 설정이 부적절한 경우 발생하는 취약점이다. "
            "주요 사례: 기본 관리자 계정 미변경, 디렉토리 리스팅 활성화, 불필요한 기능 활성화, "
            "에러 메시지에 상세 정보 노출, S3 버킷 퍼블릭 설정. "
            "대응방안: 보안 하드닝 가이드 적용, 최소 설치 원칙, 정기적 보안 설정 점검, "
            "IaC(Infrastructure as Code)로 보안 설정 코드화, CSPM 도구 활용."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A06:2021 취약하고 오래된 컴포넌트",
        "text": (
            "OWASP A06:2021 Vulnerable and Outdated Components (취약하고 오래된 컴포넌트): "
            "알려진 취약점이 있는 라이브러리, 프레임워크, 소프트웨어를 사용하는 경우의 취약점이다. "
            "주요 사례: Log4j(CVE-2021-44228), Spring4Shell, Apache Struts 취약점. "
            "대응방안: SCA(Software Composition Analysis) 도구 사용(Snyk, Dependabot), "
            "SBOM(Software Bill of Materials) 관리, 정기적 의존성 업데이트, "
            "보안 패치 모니터링(NVD, KISA 보안공지), 미사용 의존성 제거."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A07:2021 인증 및 식별 실패",
        "text": (
            "OWASP A07:2021 Identification and Authentication Failures (인증 및 식별 실패): "
            "인증 메커니즘의 취약점으로 공격자가 신원을 위조하거나 다른 사용자 계정에 접근할 수 있다. "
            "주요 사례: 크리덴셜 스터핑, 약한 비밀번호 허용, 세션 고정, "
            "비밀번호 평문 저장, MFA 미적용. "
            "대응방안: 다중 인증(MFA) 적용, 비밀번호 복잡성 정책, "
            "계정 잠금(Account Lockout), 안전한 세션 관리, 비밀번호 유출 DB 확인."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A08:2021 소프트웨어 및 데이터 무결성 실패",
        "text": (
            "OWASP A08:2021 Software and Data Integrity Failures "
            "(소프트웨어 및 데이터 무결성 실패): "
            "소프트웨어 업데이트, CI/CD 파이프라인, 직렬화 데이터의 무결성을 "
            "검증하지 않는 경우 발생하는 취약점이다. "
            "주요 사례: 안전하지 않은 역직렬화, 무결성 검증 없는 자동 업데이트, "
            "CI/CD 파이프라인 변조. "
            "대응방안: 코드 서명, 의존성 무결성 검증(checksum), "
            "CI/CD 보안 강화, 역직렬화 입력 검증."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A09:2021 보안 로깅 및 모니터링 실패",
        "text": (
            "OWASP A09:2021 Security Logging and Monitoring Failures "
            "(보안 로깅 및 모니터링 실패): "
            "보안 이벤트에 대한 로깅·모니터링이 부족하여 공격을 탐지·대응하지 못하는 취약점이다. "
            "평균 침해 탐지 시간이 200일 이상인 주요 원인이 된다. "
            "대응방안: 로그인 실패, 접근 제어 실패, 입력 검증 실패 등 보안 이벤트 로깅, "
            "중앙 로그 관리(SIEM) 도입, 실시간 경고 체계 구축, "
            "로그 무결성 보장 및 충분한 보관 기간(최소 6개월) 확보."
        ),
    },
    {
        "guide_name": "OWASP Top 10",
        "standard": "OWASP",
        "section": "A10:2021 서버 사이드 요청 위조",
        "text": (
            "OWASP A10:2021 Server-Side Request Forgery(SSRF) "
            "(서버 사이드 요청 위조): "
            "서버가 사용자 입력 URL을 검증 없이 요청하여 내부 시스템에 접근할 수 있는 취약점이다. "
            "클라우드 환경에서 메타데이터 서비스(169.254.169.254) 접근이 대표적이다. "
            "대응방안: URL 허용 목록(Allowlist) 적용, 내부 IP 대역 차단, "
            "DNS 리바인딩 방어, 클라우드 IMDS v2 적용, "
            "네트워크 세그먼테이션으로 서버의 외부 접근 범위 제한."
        ),
    },

    # --- 네트워크 보안 ---
    {
        "guide_name": "네트워크 보안 가이드",
        "standard": "KISA",
        "section": "방화벽 정책 관리",
        "text": (
            "네트워크 방화벽 정책 관리 가이드: "
            "방화벽 정책은 기본 거부(Default Deny) 원칙을 적용하여 허용된 트래픽만 통과시킨다. "
            "정책은 출발지IP, 목적지IP, 포트, 프로토콜 기반으로 설정하며, "
            "any-any 정책은 금지한다. 분기 1회 이상 미사용 정책 점검 및 정리를 수행하고, "
            "정책 변경 시 변경관리 절차를 준수한다. "
            "로그를 활성화하여 차단·허용 이벤트를 기록하고 분석해야 한다."
        ),
    },
    {
        "guide_name": "네트워크 보안 가이드",
        "standard": "KISA",
        "section": "네트워크 분리",
        "text": (
            "네트워크 분리(세그먼테이션) 가이드: "
            "DMZ, 업무 네트워크, 개발 네트워크, 관리 네트워크를 물리적 또는 "
            "논리적(VLAN)으로 분리해야 한다. "
            "인터넷 접근이 필요한 서버는 DMZ에 배치하고, DB 서버는 내부 네트워크에 배치한다. "
            "네트워크 간 통신은 방화벽을 통해 필요한 포트만 허용한다. "
            "개인정보처리시스템은 인터넷 망과 분리하거나 접근통제를 강화해야 한다. "
            "망분리 의무 대상: 정보통신망법 시행령 제15조에 따른 일정 규모 이상 사업자."
        ),
    },
    {
        "guide_name": "네트워크 보안 가이드",
        "standard": "KISA",
        "section": "VPN 보안",
        "text": (
            "VPN 보안 가이드: "
            "원격 접속 시 SSL VPN 또는 IPSec VPN을 사용하여 통신을 암호화해야 한다. "
            "VPN 접속 시 다중 인증(MFA)을 적용하고, 접속 가능한 사용자·시간·IP를 제한한다. "
            "VPN 장비의 보안 패치를 최신으로 유지하며, 접속 로그를 기록·모니터링한다. "
            "Split Tunneling은 보안 위험이 높으므로 Full Tunneling을 권장한다."
        ),
    },

    # --- 클라우드 보안 ---
    {
        "guide_name": "클라우드 보안 가이드",
        "standard": "KISA/CSA",
        "section": "AWS 보안 설정",
        "text": (
            "AWS 클라우드 보안 설정 가이드: "
            "1) IAM: 루트 계정에 MFA 활성화, IAM 사용자별 최소 권한 정책 적용, "
            "Access Key 주기적 교체(90일). "
            "2) S3: 버킷 기본 퍼블릭 접근 차단(Block Public Access), "
            "서버측 암호화(SSE-S3/SSE-KMS) 활성화, 버킷 정책으로 접근 제어. "
            "3) VPC: Security Group에서 인바운드 0.0.0.0/0 SSH(22) 금지, "
            "서브넷을 퍼블릭/프라이빗으로 분리, NAT Gateway 활용. "
            "4) CloudTrail: 모든 리전에서 API 로깅 활성화, S3에 로그 보관. "
            "5) GuardDuty: 위협 탐지 서비스 활성화."
        ),
    },
    {
        "guide_name": "클라우드 보안 가이드",
        "standard": "KISA/CSA",
        "section": "컨테이너 보안",
        "text": (
            "컨테이너 보안 가이드: "
            "1) 이미지 보안: 공식 베이스 이미지 사용, 이미지 취약점 스캔(Trivy, Clair), "
            "불필요한 패키지 제거, non-root 사용자로 실행. "
            "2) 런타임 보안: 읽기 전용 파일시스템, 리소스 제한(CPU/메모리), "
            "Seccomp/AppArmor 프로파일 적용, Privileged 모드 금지. "
            "3) 오케스트레이션(K8s): RBAC 적용, Network Policy로 Pod 간 통신 제어, "
            "Secret 관리(외부 Vault 연동), Pod Security Standards 적용. "
            "4) 레지스트리: 프라이빗 레지스트리 사용, 이미지 서명 검증."
        ),
    },

    # --- 데이터 보호 ---
    {
        "guide_name": "데이터 보호 가이드",
        "standard": "KISA",
        "section": "데이터 분류 및 관리",
        "text": (
            "데이터 분류 및 관리 가이드: "
            "데이터를 기밀성 수준에 따라 분류해야 한다: "
            "1등급(극비): 유출 시 조직에 심대한 피해, 최소 접근 원칙 적용. "
            "2등급(대외비): 내부 업무용, 부서 단위 접근 통제. "
            "3등급(일반): 공개 가능한 정보. "
            "각 등급별 저장·전송·폐기 기준을 수립하고, "
            "DLP(Data Loss Prevention) 시스템으로 중요 데이터 유출을 방지한다. "
            "개인정보는 개인정보 보호법에 따라 별도로 관리한다."
        ),
    },

    # --- 보안 감사 ---
    {
        "guide_name": "보안 감사 가이드",
        "standard": "KISA",
        "section": "취약점 점검",
        "text": (
            "취약점 점검 가이드: "
            "정기 취약점 점검은 최소 연 1회 수행하며, 신규 시스템 도입·변경 시 수시 점검한다. "
            "점검 항목: 서버(KISA 주요정보통신기반시설 기술적 취약점 분석·평가 가이드 기준), "
            "네트워크 장비, 웹 애플리케이션(OWASP Top 10), 데이터베이스, 클라우드 환경. "
            "취약점 심각도를 CVSS 기준으로 평가하고, High 이상은 1개월 이내 조치해야 한다. "
            "점검 결과 보고서를 작성하여 경영진에 보고하고, 조치 결과를 추적·관리한다."
        ),
    },
    {
        "guide_name": "보안 감사 가이드",
        "standard": "KISA",
        "section": "모의해킹",
        "text": (
            "모의해킹(Penetration Testing) 가이드: "
            "모의해킹은 실제 공격 기법을 활용하여 시스템의 보안 취약점을 검증하는 활동이다. "
            "유형: 블랙박스(외부 관점), 화이트박스(내부 정보 제공), 그레이박스(일부 정보 제공). "
            "범위: 외부 침투 테스트, 내부 침투 테스트, 웹/모바일 앱 테스트, 소셜 엔지니어링. "
            "PTES(Penetration Testing Execution Standard) 방법론에 따라 수행하며, "
            "사전 승인, 범위 합의, 비상연락체계 수립 후 진행한다. "
            "발견된 취약점은 즉시 보고하고 증적 자료를 확보해야 한다."
        ),
    },
]


BUILTIN_SECURITY_INCIDENTS: list[dict] = [
    {
        "guide_name": "보안 사고 사례집",
        "standard": "KISA",
        "section": "랜섬웨어 공격 대응",
        "text": (
            "랜섬웨어 공격 대응 사례: "
            "랜섬웨어는 파일을 암호화하고 복호화 대가로 금전을 요구하는 악성코드이다. "
            "주요 감염 경로: 피싱 이메일(첨부파일·링크), 원격 데스크톱(RDP) 취약점, "
            "VPN 취약점, 소프트웨어 공급망 공격. "
            "대응 절차: 1) 감염 시스템 즉시 네트워크 격리, 2) 감염 범위 파악, "
            "3) KISA(118) 및 경찰 신고, 4) 백업을 통한 복구, 5) 원인 분석 및 재발 방지. "
            "예방 대책: 3-2-1 백업 원칙(3개 복사본, 2종 매체, 1개 오프라인), "
            "이메일 보안 솔루션, OS·SW 보안 패치, 관리자 계정 MFA 적용."
        ),
    },
    {
        "guide_name": "보안 사고 사례집",
        "standard": "KISA",
        "section": "개인정보 유출 사고 대응",
        "text": (
            "개인정보 유출 사고 대응 사례: "
            "개인정보 유출 발생 시 개인정보 보호법 제34조에 따라 "
            "정보주체에게 유출 사실을 통지해야 한다(유출 항목, 시점, 대응조치 등). "
            "1천명 이상 유출 시 개인정보보호위원회 또는 KISA에 신고(72시간 이내). "
            "대응 절차: 1) 유출 경로 차단, 2) 유출 범위·규모 파악, "
            "3) 정보주체 통지 및 신고, 4) 피해 구제(사과문, 보상), "
            "5) 원인 분석 및 보호 조치 강화. "
            "과태료: 안전조치 미이행 시 최대 5억원, "
            "신고·통지 미이행 시 최대 5천만원의 과태료가 부과될 수 있다."
        ),
    },
    {
        "guide_name": "보안 사고 사례집",
        "standard": "KISA",
        "section": "내부자 위협 사고 대응",
        "text": (
            "내부자 위협 사고 대응 사례: "
            "내부자에 의한 정보 유출은 전체 보안 사고의 상당 부분을 차지한다. "
            "유형: 악의적 유출(경쟁사 이직 시 자료 반출), 과실에 의한 유출(이메일 오발송), "
            "계정 도용(퇴직자 계정 미삭제). "
            "대응 방안: DLP 시스템으로 USB·이메일·클라우드 반출 모니터링, "
            "UEBA(User and Entity Behavior Analytics)로 이상 행위 탐지, "
            "직무 분리(SoD) 원칙 적용, 정기적 접근권한 검토, "
            "퇴직 프로세스에서 즉시 계정 비활성화 및 자산 회수."
        ),
    },
    {
        "guide_name": "보안 사고 사례집",
        "standard": "KISA",
        "section": "DDoS 공격 대응",
        "text": (
            "DDoS(분산 서비스 거부) 공격 대응 사례: "
            "DDoS 공격은 대량의 트래픽으로 서비스 가용성을 마비시키는 공격이다. "
            "유형: 볼류메트릭 공격(UDP Flood, ICMP Flood), "
            "프로토콜 공격(SYN Flood, Ping of Death), "
            "애플리케이션 공격(HTTP Flood, Slowloris). "
            "대응 방안: 1) ISP와 협력하여 트래픽 우회(Black Hole Routing), "
            "2) Anti-DDoS 솔루션 또는 CDN(CloudFlare, AWS Shield) 활용, "
            "3) 트래픽 임계값 설정 및 자동 차단, "
            "4) 비상 연락 체계 및 서비스 대체 운영 계획 수립. "
            "KISA DDoS 사이버대피소 서비스를 활용할 수 있다."
        ),
    },
    {
        "guide_name": "보안 사고 사례집",
        "standard": "KISA",
        "section": "피싱 공격 대응",
        "text": (
            "피싱(Phishing) 공격 대응 사례: "
            "피싱은 신뢰할 수 있는 기관을 사칭하여 개인정보·인증정보를 탈취하는 공격이다. "
            "유형: 이메일 피싱, 스피어 피싱(특정 대상), 스미싱(SMS), 보이스 피싱. "
            "대응 방안: 1) 이메일 보안(SPF, DKIM, DMARC) 설정, "
            "2) 의심 이메일 신고 체계 운영, 3) 정기적 피싱 시뮬레이션 훈련, "
            "4) URL 필터링 및 샌드박스 분석, 5) 임직원 보안 인식 교육(연 2회 이상). "
            "피싱 메일 수신 시: 링크 클릭 금지 → IT보안팀 신고 → 계정 비밀번호 변경."
        ),
    },
]


async def ingest_builtin_security_knowledge() -> dict[str, int]:
    """
    내장 보안 지식베이스를 벡터 DB에 적재

    Returns:
        컬렉션별 적재된 청크 수
    """
    logger.info("내장 보안 지식베이스 적재 시작")

    vector_store = get_vector_store()
    results = {"security_guides": 0, "security_incidents": 0}

    # 보안 가이드 적재
    guide_texts = [item["text"] for item in BUILTIN_SECURITY_GUIDES]
    guide_embeddings = await embed_batch(guide_texts)

    guide_ids = [
        f"builtin_guide_{i}" for i in range(len(BUILTIN_SECURITY_GUIDES))
    ]
    guide_metadatas = [
        {
            "source": "builtin",
            "source_type": "security_guide",
            "guide_name": item["guide_name"],
            "standard": item["standard"],
            "section": item["section"],
        }
        for item in BUILTIN_SECURITY_GUIDES
    ]

    vector_store.upsert_and_cleanup(
        collection_name="security_guides",
        id_prefix="builtin_guide_",
        documents=guide_texts,
        metadatas=guide_metadatas,
        ids=guide_ids,
        embeddings=guide_embeddings,
    )
    results["security_guides"] = len(BUILTIN_SECURITY_GUIDES)

    logger.info("보안 가이드 적재 완료", count=len(BUILTIN_SECURITY_GUIDES))

    # 보안 사고 사례 적재
    incident_texts = [item["text"] for item in BUILTIN_SECURITY_INCIDENTS]
    incident_embeddings = await embed_batch(incident_texts)

    incident_ids = [
        f"builtin_incident_{i}" for i in range(len(BUILTIN_SECURITY_INCIDENTS))
    ]
    incident_metadatas = [
        {
            "source": "builtin",
            "source_type": "security_incident",
            "guide_name": item["guide_name"],
            "standard": item["standard"],
            "section": item["section"],
        }
        for item in BUILTIN_SECURITY_INCIDENTS
    ]

    vector_store.upsert_and_cleanup(
        collection_name="security_incidents",
        id_prefix="builtin_incident_",
        documents=incident_texts,
        metadatas=incident_metadatas,
        ids=incident_ids,
        embeddings=incident_embeddings,
    )
    results["security_incidents"] = len(BUILTIN_SECURITY_INCIDENTS)

    logger.info("보안 사고 사례 적재 완료", count=len(BUILTIN_SECURITY_INCIDENTS))
    logger.info("내장 보안 지식베이스 적재 완료", results=results)

    return results


async def ingest_all_security_data(
    guides_dir: str | None = None,
    incidents_dir: str | None = None,
) -> dict:
    """
    전체 보안 데이터 적재 (내장 지식베이스 + PDF 디렉토리)

    Args:
        guides_dir: 보안 가이드 PDF 디렉토리 경로 (선택)
        incidents_dir: 보안 사고 사례 PDF 디렉토리 경로 (선택)

    Returns:
        적재 결과 요약
    """
    logger.info("전체 보안 데이터 적재 시작")

    results = {
        "builtin": {},
        "guide_pdfs": {},
        "incident_pdfs": {},
    }

    # 1. 내장 지식베이스 적재
    results["builtin"] = await ingest_builtin_security_knowledge()

    # 2. 보안 가이드 PDF 적재
    if guides_dir:
        guides_path = Path(guides_dir)
        if guides_path.exists() and guides_path.is_dir():
            results["guide_pdfs"] = await ingest_security_directory(
                guides_dir,
                standard="",
                collection="security_guides",
            )
        else:
            logger.warning("보안 가이드 디렉토리 없음", dir_path=guides_dir)

    # 3. 보안 사고 사례 PDF 적재
    if incidents_dir:
        incidents_path = Path(incidents_dir)
        if incidents_path.exists() and incidents_path.is_dir():
            results["incident_pdfs"] = await ingest_security_directory(
                incidents_dir,
                standard="",
                collection="security_incidents",
            )
        else:
            logger.warning("보안 사고 사례 디렉토리 없음", dir_path=incidents_dir)

    logger.info("전체 보안 데이터 적재 완료", results=results)
    return results
