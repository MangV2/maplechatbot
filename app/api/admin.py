"""관리 API: 크롤링 트리거 및 상태 조회."""
import asyncio
import logging
from threading import Thread

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.crawler.pipeline import CrawlPipeline
from app.crawler.scheduler import get_scheduler_status, _is_running

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
