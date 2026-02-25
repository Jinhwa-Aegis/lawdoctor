# CLAUDE.md — 법무주치의 프로젝트 컨텍스트

> Claude Code가 이 프로젝트의 코드를 작성·수정·리뷰할 때 참조하는 컨텍스트 문서입니다.

---

## 프로젝트 개요

**법무주치의**는 이지스엔터프라이즈 내부 직원(10~30명)을 위한 AI 기반 법률 자문 웹 서비스입니다.
외부 변호사 자문 비용을 절감하기 위해, RAG 기반 법률 Q&A 챗봇과 계약서 리뷰 기능을 제공합니다.

## 기술 스택

- **Backend:** Python 3.11+ / FastAPI
- **Frontend:** React (Vite, JavaScript)
- **LLM:** OpenAI API (gpt-4o) — 향후 로컬 LLM 전환 가능성 있음
- **임베딩:** OpenAI text-embedding-3-small 또는 Upstage embedding
- **벡터 DB:** ChromaDB (로컬, 온프레미스 배포)
- **RDB:** PostgreSQL (사용자, 채팅 이력, 피드백)
- **PDF 파싱:** PyMuPDF (fitz)
- **법령 데이터:** 국가법령정보센터 Open API

## 핵심 아키텍처

```
사용자 → React Frontend → FastAPI Backend
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
              [Q&A 챗봇]  [계약서 리뷰]  [관리]
                    │         │
                    ▼         ▼
              [RAG Pipeline]  [문서 분석]
                    │         │
                    ▼         ▼
              [ChromaDB]  [OpenAI API]
              (법령+자문)
```

## 디렉토리 구조

```
법무주치의/
├── CLAUDE.md
├── backend/
│   ├── main.py              # FastAPI 진입점
│   ├── config.py            # 환경 설정 (.env 로드)
│   ├── api/                 # 라우터 (chat, review, feedback, admin)
│   ├── core/                # 비즈니스 로직 (rag, llm, classifier, contract_reviewer)
│   ├── data/                # 데이터 처리 (PDF 파싱, 법령 API, 벡터 스토어)
│   ├── models/              # SQLAlchemy 모델
│   └── db/                  # DB 연결 및 마이그레이션
├── frontend/
│   ├── src/pages/           # ChatPage, ReviewPage, AdminPage
│   ├── src/components/      # ChatMessage, FeedbackButton, FileUpload, RiskReport
│   └── src/api/             # API 클라이언트
└── data/
    ├── consultations/       # 기존 변호사 자문 PDF (50건 이하)
    └── laws/                # 법령 데이터 캐시
```

## 코딩 규칙

### 공통
- 한국어 주석 사용 (코드 자체는 영어 변수명)
- 환경변수는 `.env` 파일로 관리, 코드에 API 키 하드코딩 금지
- 에러 메시지는 한국어로 사용자에게 표시

### Backend (Python)
- FastAPI 라우터는 `api/` 디렉토리에 기능별 분리
- Pydantic v2 모델 사용 (request/response 스키마)
- 비동기(async) 우선, 동기 블로킹 작업은 `run_in_executor` 사용
- 타입 힌트 필수
- 로깅: `structlog` 사용, 모든 LLM 호출에 대해 요청/응답 로그 기록
- DB: SQLAlchemy 2.0 async, Alembic 마이그레이션

### Frontend (React)
- 함수형 컴포넌트 + Hooks
- 상태 관리: React 내장 (useState, useContext) — 별도 상태 관리 라이브러리 불필요
- API 호출: fetch 또는 axios
- 스타일링: Tailwind CSS
- 채팅 UI: 스트리밍 응답 지원 (SSE)

### LLM 호출 규칙
- 모든 OpenAI API 호출은 `core/llm.py`를 통해 수행 (직접 호출 금지)
- 시스템 프롬프트에 반드시 면책 문구 포함
- 응답에 근거 법령 인용을 강제하는 프롬프트 설계
- API 호출 실패 시 3회 재시도 후 사용자에게 오류 안내

## 법률 도메인 규칙

### 4개 법률 분야
1. **개인정보보호** — 개인정보보호법, 정보통신망법
2. **계약 검토** — 민법, 상법, 전자문서법
3. **공동주택관리법** — 공동주택관리법, 주택법
4. **소송·분쟁** — 민사소송법 등 (**경영진 전용, 접근 제한 필수**)

### 에스컬레이션 (고위험 감지)
다음 키워드가 질의에 포함되면 AI 답변에 "외부 자문 필요" 안내를 표시:
- 소송, 고소, 고발, 형사, 과태료, 벌금, 압수수색
- 손해배상, 가처분, 가압류, 강제집행
- 개인정보보호위원회 조사, 시정명령, 과징금

### 면책 문구 (모든 AI 답변에 필수)
```
⚠️ 본 답변은 AI가 생성한 참고 정보이며, 법적 효력이 있는 공식 법률 자문이 아닙니다.
중요한 법률적 판단이 필요한 경우 외부 전문가 자문을 받으시기 바랍니다.
```

## 보안 규칙

- **IP 제한:** 사내 네트워크에서만 접근 가능 (MVP)
- **소송 데이터:** 경영진 역할(role)만 접근 가능, API 레벨에서 권한 체크 필수
- **API 키:** `.env`에만 저장, `.gitignore`에 `.env` 포함
- **업로드 파일:** 분석 완료 후 24시간 내 자동 삭제
- **LLM 전송 제외:** 주민등록번호, 계좌번호 등 직접적 개인식별정보는 API 전송 전 마스킹 (Phase 2)
- **소송 관련 데이터:** 외부 API 전송 금지 (MVP에서는 소송 분야 자체를 AI 답변 대상에서 제외)

## 데이터 소스

| 데이터 | 위치 | 형태 | 용도 |
|--------|------|------|------|
| 변호사 자문 이력 | `data/consultations/` | PDF (50건 이하) | RAG 지식 베이스 |
| 법령 데이터 | 국가법령정보센터 API | JSON/XML | RAG 지식 베이스 |
| 사용자 채팅 이력 | PostgreSQL `chat_histories` | DB 레코드 | 대화 이력 관리 |
| 피드백 | PostgreSQL `feedbacks` | DB 레코드 | 품질 관리 |

## 개발 우선순위

### MVP (4주)
1. PDF 파싱 → 벡터 DB 적재 파이프라인
2. 국가법령정보센터 API 연동 → 법령 벡터 DB 적재
3. RAG 기반 Q&A 챗봇 (채팅 UI + 스트리밍)
4. 계약서 업로드 + 리스크 분석
5. 피드백(👍/👎) 시스템
6. 권한 관리 (IP 제한 + 역할별 접근)

### Phase 2
- 법률 문서 초안 생성
- 자문 이력 전문 검색
- 판례 연동
- 민감 정보 마스킹
- 법령 변경 알림

## 테스트 전략

- Backend: pytest (API 엔드포인트 + 핵심 로직)
- Frontend: 수동 테스트 (MVP)
- RAG 품질: 사전 정의된 Q&A 세트로 답변 정확도 측정 (최소 20개)

## 배포

- 온프레미스 서버에 Docker Compose로 배포
- 서비스 구성: backend, frontend (nginx), postgresql, chromadb
- `docker-compose.yml`로 원커맨드 배포 목표
