"""FastAPI 앱 진입점."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.sessions import router as sessions_router
from app.config import settings
from app.crawler.scheduler import start_scheduler, stop_scheduler
from app.database import Base, engine
from app.schemas.chat import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# DB 연결 재시도 (Docker Compose에서 Postgres 준비 전 기동 대응)
_MAX_DB_RETRIES = 10
_DB_RETRY_INTERVAL = 2


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 테이블 생성 + 크롤링 스케줄러 시작."""
    for attempt in range(1, _MAX_DB_RETRIES + 1):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables ready.")
            break
        except Exception as e:
            if attempt == _MAX_DB_RETRIES:
                logger.error("Database unavailable after %d attempts: %s", _MAX_DB_RETRIES, e)
                raise
            logger.warning("Database not ready (attempt %d/%d), retrying in %ds: %s", attempt, _MAX_DB_RETRIES, _DB_RETRY_INTERVAL, e)
            await asyncio.sleep(_DB_RETRY_INTERVAL)

    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    description="메이플스토리 RAG 챗봇 API — Qdrant + GPT-4o 기반",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 미들웨어
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인으로 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(admin_router)


@app.get("/health", response_model=HealthResponse)
def health():
    """헬스 체크 (Qdrant 연결 상태 포함)."""
    try:
        from app.rag.qdrant_store import QdrantStore

        store = QdrantStore()
        count = store.count()
        return HealthResponse(
            status="ok", qdrant_status="connected", document_count=count
        )
    except Exception as e:
        return HealthResponse(
            status="degraded", qdrant_status=f"error: {e}", document_count=0
        )
