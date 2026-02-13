"""주간 크롤링 스케줄러 (APScheduler)."""
import logging
from collections import deque
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.crawler.pipeline import CrawlPipeline, PipelineResult

logger = logging.getLogger(__name__)

CRAWL_HISTORY_MAX = 50

_scheduler: BackgroundScheduler | None = None
_last_result: PipelineResult | None = None
_last_run_at: datetime | None = None
_is_running: bool = False
_crawl_history: deque = deque(maxlen=CRAWL_HISTORY_MAX)


def _push_crawl_history(triggered_by: str, run_at: datetime, result: PipelineResult):
    """크롤링 이력에 한 건 추가."""
    _crawl_history.append({
        "run_at": run_at.isoformat(),
        "triggered_by": triggered_by,
        "crawled": result.crawled,
        "upserted": result.upserted,
        "errors": result.errors,
        "elapsed_seconds": round(result.elapsed_seconds, 1),
    })


def get_crawl_history() -> list[dict]:
    """최근 크롤링 이력 (최신순)."""
    return list(reversed(_crawl_history))


def _run_weekly_crawl():
    """주간 크롤링 작업 (스케줄러에서 호출)."""
    global _last_result, _last_run_at, _is_running

    if _is_running:
        logger.warning("이전 크롤링이 아직 진행 중입니다. 건너뜁니다.")
        return

    _is_running = True
    _last_run_at = datetime.now()
    logger.info("=== 주간 자동 크롤링 시작 (%s) ===", _last_run_at.isoformat())

    try:
        pipeline = CrawlPipeline()
        _last_result = pipeline.run_sync(
            max_jobs_per_group=None,  # 전체 직업
            max_pages=2,             # 직업당 2페이지
            max_posts_per_page=20,   # 페이지당 최대 20개
        )
        _push_crawl_history("scheduled", _last_run_at, _last_result)
        logger.info(
            "주간 크롤링 완료: 크롤링 %d → 적재 %d (에러 %d)",
            _last_result.crawled, _last_result.upserted, _last_result.errors,
        )
    except Exception as e:
        logger.exception("주간 크롤링 실패: %s", e)
        _last_result = PipelineResult(errors=1)
        _push_crawl_history("scheduled", _last_run_at, _last_result)
    finally:
        _is_running = False


def start_scheduler():
    """스케줄러 시작 (매주 월요일 AM 3:00 KST)."""
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.info("스케줄러가 이미 실행 중입니다.")
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    _scheduler.add_job(
        _run_weekly_crawl,
        trigger=CronTrigger(day_of_week="mon", hour=3, minute=0),
        id="weekly_crawl",
        name="주간 메이플 인벤 크롤링",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("크롤링 스케줄러 시작됨 (매주 월 03:00 KST)")


def stop_scheduler():
    """스케줄러 중지."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("크롤링 스케줄러 중지됨")


def get_scheduler_status() -> dict:
    """스케줄러 상태 조회."""
    next_run = None
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("weekly_crawl")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return {
        "scheduler_running": bool(_scheduler and _scheduler.running),
        "is_crawling": _is_running,
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "next_run_at": next_run,
        "last_result": {
            "crawled": _last_result.crawled if _last_result else 0,
            "upserted": _last_result.upserted if _last_result else 0,
            "errors": _last_result.errors if _last_result else 0,
            "elapsed_seconds": _last_result.elapsed_seconds if _last_result else 0,
        } if _last_result else None,
    }
