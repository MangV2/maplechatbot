"""주간 크롤링 스케줄러 (APScheduler)."""
import logging
from collections import deque
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import desc

from app.crawler.pipeline import CrawlPipeline, PipelineResult
from app.database import SessionLocal
from app.models.crawl_history import CrawlHistory

logger = logging.getLogger(__name__)

CRAWL_HISTORY_LIMIT = 100
CRAWL_LOG_MAX = 500

_scheduler: BackgroundScheduler | None = None
_last_result: PipelineResult | None = None
_last_run_at: datetime | None = None
_is_running: bool = False
# 진행 중일 때만 의미 있음: 완료된 직업/게시판 수, 전체 수
_crawl_progress: dict = {"jobs_done": 0, "jobs_total": 0}
_crawl_log_buffer: deque = deque(maxlen=CRAWL_LOG_MAX)
_crawl_log_handler_attached: bool = False


class CrawlLogHandler(logging.Handler):
    """app.crawler 로거 메시지를 버퍼에 쌓음."""

    def __init__(self, buffer: deque):
        super().__init__()
        self.buffer = buffer
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord):
        try:
            self.buffer.append(self.format(record))
        except Exception:
            pass


def _ensure_crawl_log_handler():
    """app.crawler 로거에 CrawlLogHandler 한 번만 부착."""
    global _crawl_log_handler_attached
    if _crawl_log_handler_attached:
        return
    crawler_logger = logging.getLogger("app.crawler")
    crawler_logger.addHandler(CrawlLogHandler(_crawl_log_buffer))
    _crawl_log_handler_attached = True


def get_recent_crawl_logs() -> list[str]:
    """최근 크롤 로그 라인 목록 (API/UI용)."""
    _ensure_crawl_log_handler()
    return list(_crawl_log_buffer)


def set_crawl_running(running: bool):
    """수동 크롤 시 is_crawling 상태 설정."""
    global _is_running
    _is_running = running


def set_crawl_progress(jobs_done: int, jobs_total: int):
    """크롤 진행 상황 갱신 (API/UI에서 조회용)."""
    global _crawl_progress
    _crawl_progress = {"jobs_done": jobs_done, "jobs_total": jobs_total}


def _push_crawl_history(triggered_by: str, run_at: datetime, result: PipelineResult):
    """크롤링 이력을 DB에 저장."""
    db = SessionLocal()
    try:
        entry = CrawlHistory(
            run_at=run_at,
            triggered_by=triggered_by,
            crawled=result.crawled,
            upserted=result.upserted,
            skipped=result.skipped,
            errors=result.errors,
            elapsed_seconds=round(result.elapsed_seconds, 1),
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        logger.warning("크롤링 이력 저장 실패: %s", e)
        db.rollback()
    finally:
        db.close()


def get_crawl_history(limit: int = CRAWL_HISTORY_LIMIT) -> list[dict]:
    """최근 크롤링 이력 (최신순, DB 조회)."""
    db = SessionLocal()
    try:
        rows = (
            db.query(CrawlHistory)
            .order_by(desc(CrawlHistory.run_at))
            .limit(limit)
            .all()
        )
        return [
            {
                "run_at": r.run_at.isoformat(),
                "triggered_by": r.triggered_by,
                "crawled": r.crawled,
                "upserted": r.upserted,
                "skipped": r.skipped,
                "errors": r.errors,
                "elapsed_seconds": r.elapsed_seconds,
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("크롤링 이력 조회 실패: %s", e)
        return []
    finally:
        db.close()


def _run_weekly_crawl():
    """주간 크롤링 작업 (스케줄러에서 호출)."""
    global _last_result, _last_run_at, _is_running

    if _is_running:
        logger.warning("이전 크롤링이 아직 진행 중입니다. 건너뜁니다.")
        return

    _is_running = True
    _last_run_at = datetime.now()
    set_crawl_progress(0, 0)
    logger.info("=== 주간 자동 크롤링 시작 (%s) ===", _last_run_at.isoformat())

    try:
        pipeline = CrawlPipeline()
        _last_result = pipeline.run_sync(
            max_jobs_per_group=None,   # 전체 직업
            max_pages=10,              # 기간 내 수집을 위해 충분한 페이지
            max_posts_per_page=100,   # 페이지당 충분한 게시글 수
            since_date=None,           # 자동 결정 (저장된 날짜 → Qdrant 최신 작성일 → 전체 수집)
            progress_callback=set_crawl_progress,
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

    _ensure_crawl_log_handler()
    return {
        "scheduler_running": bool(_scheduler and _scheduler.running),
        "is_crawling": _is_running,
        "crawl_progress": dict(_crawl_progress),
        "recent_logs": list(_crawl_log_buffer),
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "next_run_at": next_run,
        "last_result": {
            "crawled": _last_result.crawled if _last_result else 0,
            "upserted": _last_result.upserted if _last_result else 0,
            "skipped": _last_result.skipped if _last_result else 0,
            "errors": _last_result.errors if _last_result else 0,
            "elapsed_seconds": _last_result.elapsed_seconds if _last_result else 0,
        } if _last_result else None,
    }
