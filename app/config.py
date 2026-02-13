"""애플리케이션 설정 (환경 변수 기반)."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """환경 변수에서 로드하는 설정."""

    # FastAPI
    app_name: str = "Maple RAG API"
    debug: bool = False

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""  # .env에서 설정 필수
    postgres_database: str = "maple_rag"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "maple_posts"

    # OpenAI
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"

    # RAG 설정
    rag_top_k: int = 5
    rag_max_tokens: int = 1024

    @property
    def postgres_url(self) -> str:
        """동기 PostgreSQL URL."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 기존 .env의 미사용 변수 무시 (마이그레이션 호환)


settings = Settings()
