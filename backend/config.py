"""환경 설정 — .env 파일에서 로드"""

from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    # LLM API
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://lawdoctor:lawdoctor_pass@localhost:5432/lawdoctor",
        alias="DATABASE_URL",
    )

    # ChromaDB
    chroma_host: str = Field(default="localhost", alias="CHROMA_HOST")
    chroma_port: int = Field(default=8000, alias="CHROMA_PORT")

    # 국가법령정보센터 API
    law_api_key: str = Field(default="", alias="LAW_API_KEY")

    # App
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8080, alias="APP_PORT")
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")

    # Security
    allowed_ips: str = Field(default="127.0.0.1", alias="ALLOWED_IPS")
    secret_key: str = Field(default="change-me-in-production", alias="SECRET_KEY")

    # Upload
    upload_dir: str = Field(default="./uploads", alias="UPLOAD_DIR")
    max_upload_size_mb: int = Field(default=50, alias="MAX_UPLOAD_SIZE_MB")
    upload_cleanup_hours: int = Field(default=24, alias="UPLOAD_CLEANUP_HOURS")

    # LLM 모델 설정
    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    query_rewrite_model: str = Field(default="gpt-4o-mini", alias="QUERY_REWRITE_MODEL")

    # RAG 파이프라인 설정
    enable_query_rewrite: bool = Field(default=True, alias="ENABLE_QUERY_REWRITE")
    enable_multihop: bool = Field(default=True, alias="ENABLE_MULTIHOP")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.app_env == "production":
            if self.secret_key == "change-me-in-production":
                raise ValueError("SECRET_KEY must be changed in production")
            if "lawdoctor_pass" in self.database_url:
                raise ValueError("Default database credentials must not be used in production")
        return self


settings = Settings()
