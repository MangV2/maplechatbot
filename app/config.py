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

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_auth_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"
    google_userinfo_url: str = "https://www.googleapis.com/oauth2/v2/userinfo"

    # JWT (로그인 세션)
    jwt_secret: str = ""
    jwt_algorithm: str = ""
    jwt_expire_hours: int = 168  # 7일

    # 프론트엔드 URL (로그인 후 리다이렉트)
    frontend_url: str = "http://localhost:8501"

    # OAuth 콜백 URL (API 서버 주소. Google Cloud에 등록한 Redirect URI와 일치해야 함)
    auth_redirect_base: str = "http://localhost:8000"

    # Nexon Open API (메이플스토리 캐릭터 정보)
    nexon_open_api_key: str = ""

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
