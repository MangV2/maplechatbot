"""관리 API: 크롤링 트리거, 상태 조회, Qdrant 현황, 헬스, 크롤링 이력."""
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.crawler.pipeline import CrawlPipeline
from app.crawler.scheduler import get_scheduler_status, get_crawl_history, _is_running, _push_crawl_history
from app.rag.qdrant_store import QdrantStore
from app.schemas.chat import HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── 스키마 ─────────────────────────────────────────────

class CrawlTriggerRequest(BaseModel):
    """수동 크롤링 트리거 요청."""

    max_jobs_per_group: int | None = Field(
        default=3, description="직업군당 최대 직업 수 (null이면 전체)"
    )
    max_pages: int = Field(default=1, ge=1, le=10, description="직업별 페이지 수")
    max_posts_per_page: int = Field(
        default=10, ge=1, le=50, description="페이지당 최대 게시글 수"
    )


class CrawlStatusResponse(BaseModel):
    """크롤링 상태 응답."""

    scheduler_running: bool
    is_crawling: bool
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_result: dict | None = None


class CrawlTriggerResponse(BaseModel):
    """크롤링 트리거 응답."""

    message: str
    crawled: int = 0
    upserted: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0


class CrawlHistoryEntry(BaseModel):
    run_at: str
    triggered_by: str
    crawled: int
    upserted: int
    errors: int
    elapsed_seconds: float


class CrawlHistoryResponse(BaseModel):
    history: list[CrawlHistoryEntry]


class QdrantStatsResponse(BaseModel):
    points_count: int
    jobs: dict[str, int]
    groups: dict[str, int]


class QdrantDocumentsResponse(BaseModel):
    items: list[dict]
    next_offset: int | str | None = None


# ── 엔드포인트 ─────────────────────────────────────────

@router.get("/crawl/status", response_model=CrawlStatusResponse)
async def crawl_status():
    """크롤링 스케줄러 및 마지막 실행 상태 조회."""
    return CrawlStatusResponse(**get_scheduler_status())


@router.post("/crawl", response_model=CrawlTriggerResponse)
async def trigger_crawl(request: CrawlTriggerRequest):
    """수동으로 크롤링 파이프라인을 실행합니다."""
    if _is_running:
        raise HTTPException(
            status_code=409, detail="크롤링이 이미 진행 중입니다."
        )

    try:
        logger.info(
            "수동 크롤링 트리거: jobs=%s, pages=%d, posts=%d",
            request.max_jobs_per_group, request.max_pages, request.max_posts_per_page,
        )
        pipeline = CrawlPipeline()
        result = await pipeline.run(
            max_jobs_per_group=request.max_jobs_per_group,
            max_pages=request.max_pages,
            max_posts_per_page=request.max_posts_per_page,
        )
        _push_crawl_history("manual", datetime.now(), result)
        return CrawlTriggerResponse(
            message="크롤링 완료",
            crawled=result.crawled,
            upserted=result.upserted,
            errors=result.errors,
            elapsed_seconds=round(result.elapsed_seconds, 1),
        )
    except Exception as e:
        logger.exception("수동 크롤링 실패: %s", e)
        raise HTTPException(
            status_code=500, detail=f"크롤링 실패: {str(e)}"
        )


@router.get("/crawl/history", response_model=CrawlHistoryResponse)
async def crawl_history():
    """최근 크롤링 이력 (최신순)."""
    return CrawlHistoryResponse(history=get_crawl_history())


@router.get("/health", response_model=HealthResponse)
def admin_health():
    """헬스 체크 (Qdrant 연결 포함)."""
    try:
        store = QdrantStore()
        count = store.count()
        return HealthResponse(
            status="ok", qdrant_status="connected", document_count=count
        )
    except Exception as e:
        return HealthResponse(
            status="degraded", qdrant_status=str(e), document_count=0
        )


@router.get("/qdrant/stats", response_model=QdrantStatsResponse)
def qdrant_stats():
    """Qdrant 컬렉션 현황 (전체 수, 직업/직업군별 개수)."""
    try:
        store = QdrantStore()
        stats = store.get_job_stats()
        return QdrantStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant 조회 실패: {e}")


@router.get("/qdrant/documents", response_model=QdrantDocumentsResponse)
def qdrant_documents(
    job: str | None = Query(None, description="직업 필터"),
    job_group: str | None = Query(None, alias="직업군", description="직업군 필터"),
    limit: int = Query(20, ge=1, le=100),
    offset: str | None = Query(None, description="이전 응답의 next_offset (페이징)"),
):
    """Qdrant에 저장된 문서 목록 조회 (필터·페이징)."""
    try:
        store = QdrantStore()
        pagination_offset = None
        if offset is not None:
            try:
                pagination_offset = int(offset)
            except ValueError:
                pagination_offset = offset
        items, next_offset = store.scroll_documents(
            limit=limit,
            offset=pagination_offset,
            job=job,
            job_group=job_group,
        )
        return QdrantDocumentsResponse(items=items, next_offset=next_offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant 문서 조회 실패: {e}")
