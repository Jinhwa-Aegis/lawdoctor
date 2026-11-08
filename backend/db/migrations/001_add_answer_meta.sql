-- 답변 후처리 결과(인용 검증 결과, 후속 질문) 저장 컬럼
-- 개발 환경은 앱 시작 시 자동 적용됨 (db.database.SCHEMA_PATCHES)
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS answer_meta JSON;
