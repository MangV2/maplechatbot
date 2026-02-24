"""관리 API: 크롤링 트리거, 상태 조회, Qdrant 현황, 헬스, 크롤링 이력."""
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.crawler.pipeline import CrawlPipeline
from app.crawler.scheduler import (
    get_scheduler_status,
    get_crawl_history,
    set_crawl_progress,
    set_crawl_running,
    _is_running,
    _push_crawl_history,
)
from app.models.chat_history import ChatSession
from app.models.user import User
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
    max_pages: int = Field(default=1, ge=1, le=50, description="직업별 페이지 수")
    max_posts_per_page: int = Field(
        default=10, ge=1, le=200, description="페이지당 최대 게시글 수"
    )
    since_date: str | None = Field(
        default=None,
        description="수집 시작일 (YYYY-MM-DD 형식). None이면 자동 결정 (저장된 날짜 → Qdrant 최신 작성일 → 전체 수집)"
    )
    crawl_mode: str = Field(
        default="all",
        description="크롤링 대상: job_only(직업게시판만), flat_only(단일게시판만), all(전체)"
    )
    background: bool = Field(
        default=True,
        description="True면 백그라운드 실행 후 즉시 202 반환(진행률·로그 폴링 가능). False면 완료까지 대기."
    )


class CrawlStatusResponse(BaseModel):
    """크롤링 상태 응답."""

    scheduler_running: bool
    is_crawling: bool
    crawl_progress: dict | None = None  # {"jobs_done": int, "jobs_total": int}
    recent_logs: list[str] = []  # 크롤링 진행 로그 (app.crawler)
    last_run_at: str | None = None
    next_run_at: str | None = None
    last_result: dict | None = None


class CrawlTriggerResponse(BaseModel):
    """크롤링 트리거 응답."""

    message: str
    crawled: int = 0
    upserted: int = 0
    skipped: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0


class CrawlHistoryEntry(BaseModel):
    run_at: str
    triggered_by: str
    crawled: int
    upserted: int
    skipped: int = 0
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


class SuggestedSinceDateResponse(BaseModel):
    """수집 시작일 자동 제안 (마지막 크롤 날짜 → Qdrant 최신 문서 날짜)."""
    since_date: str | None = None  # YYYY-MM-DD, 없으면 null


class DebugSinceDateResponse(BaseModel):
    """수집 시작일 자동 결정 단계별 확인용."""
    step1_last_crawl_file_exists: bool = False
    step1_last_crawl_file_value: str | None = None
    step2_qdrant_points_count: int = 0
    step2_qdrant_max_date: str | None = None
    step2_qdrant_sample_payload_keys: list[str] = []
    step2_qdrant_sample_written_dates: list[str] = []
    step3_suggested_since_date: str | None = None
    error: str | None = None


# ── 엔드포인트 ─────────────────────────────────────────

@router.get("/crawl/debug-since-date", response_model=DebugSinceDateResponse)
def debug_since_date():
    """수집 시작일 자동 결정 단계별 확인: 1) 저장 파일 2) Qdrant 최신 날짜 3) 최종 제안값."""
    from app.crawler.pipeline import load_last_crawl_date, determine_since_date, LAST_CRAWL_DATE_FILE

    out = DebugSinceDateResponse()
    try:
        # 1단계: 저장된 마지막 크롤링 날짜 파일
        out.step1_last_crawl_file_exists = LAST_CRAWL_DATE_FILE.exists()
        if out.step1_last_crawl_file_exists:
            try:
                content = LAST_CRAWL_DATE_FILE.read_text(encoding="utf-8").strip()
                out.step1_last_crawl_file_value = content or "(비어 있음)"
            except Exception as e:
                out.step1_last_crawl_file_value = f"(읽기 실패: {e})"
        else:
            out.step1_last_crawl_file_value = None

        # 2단계: Qdrant에서 최신 날짜 + 샘플 payload
        store = QdrantStore()
        try:
            info = store.client.get_collection(store.collection_name)
            out.step2_qdrant_points_count = info.points_count
        except Exception as e:
            out.error = f"Qdrant 컬렉션 조회 실패: {e}"
            return out

        results, _ = store.client.scroll(
            collection_name=store.collection_name,
            limit=5,
            with_payload=True,
            with_vectors=False,
        )
        if results:
            out.step2_qdrant_sample_payload_keys = list((results[0].payload or {}).keys())
            for pt in results:
                p = pt.payload or {}
                for k, v in p.items():
                    if v is not None and v != "":
                        if "작성" in k or "date" in k.lower() or k == "작성일":
                            out.step2_qdrant_sample_written_dates.append(f"{k}={repr(v)}")
                if len(out.step2_qdrant_sample_written_dates) >= 5:
                    break
            if not out.step2_qdrant_sample_written_dates:
                out.step2_qdrant_sample_written_dates = [
                    f"{k}={repr((results[0].payload or {}).get(k))}" for k in out.step2_qdrant_sample_payload_keys[:10]
                ]

        max_dt = store.get_max_written_date()
        out.step2_qdrant_max_date = max_dt.strftime("%Y-%m-%d %H:%M") if max_dt else None

        # 3단계: 최종 제안값
        dt = determine_since_date(store)
        out.step3_suggested_since_date = dt.strftime("%Y-%m-%d") if dt else None
    except Exception as e:
        out.error = str(e)
    return out


@router.get("/crawl/suggested-since-date", response_model=SuggestedSinceDateResponse)
def get_suggested_since_date():
    """수집 시작일 자동 제안: 저장된 마지막 크롤 날짜 → Qdrant 최신 문서 날짜. 없으면 null."""
    from app.crawler.pipeline import determine_since_date
    store = QdrantStore()
    dt = determine_since_date(store)
    if dt is None:
        return SuggestedSinceDateResponse(since_date=None)
    return SuggestedSinceDateResponse(since_date=dt.strftime("%Y-%m-%d"))


@router.get("/crawl/status", response_model=CrawlStatusResponse)
async def crawl_status():
    """크롤링 스케줄러 및 마지막 실행 상태 조회."""
    return CrawlStatusResponse(**get_scheduler_status())


def _run_manual_crawl_sync(
    max_jobs_per_group: int | None,
    max_pages: int,
    max_posts_per_page: int,
    since_date_dt: datetime | None,
    crawl_mode: str,
):
    """백그라운드 스레드에서 실행하는 동기 크롤링."""
    set_crawl_running(True)
    set_crawl_progress(0, 0)
    try:
        pipeline = CrawlPipeline()
        result = pipeline.run_sync(
            max_jobs_per_group=max_jobs_per_group,
            max_pages=max_pages,
            max_posts_per_page=max_posts_per_page,
            since_date=since_date_dt,
            crawl_mode=crawl_mode,
            progress_callback=set_crawl_progress,
        )
        _push_crawl_history("manual", datetime.now(timezone.utc), result)
        return result
    finally:
        set_crawl_running(False)


@router.post("/crawl")
async def trigger_crawl(request: CrawlTriggerRequest):
    """수동으로 크롤링 파이프라인을 실행합니다. background=True면 백그라운드 실행 후 202 반환."""
    if _is_running:
        raise HTTPException(
            status_code=409, detail="크롤링이 이미 진행 중입니다."
        )

    since_date_dt = None
    if request.since_date:
        try:
            since_date_dt = datetime.strptime(request.since_date, "%Y-%m-%d")
            since_date_dt = since_date_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"잘못된 날짜 형식: {request.since_date}. YYYY-MM-DD 형식이어야 합니다.",
            )

    crawl_mode = request.crawl_mode if request.crawl_mode in ("job_only", "flat_only", "all") else "all"
    logger.info(
        "수동 크롤링 트리거: jobs=%s, pages=%d, posts=%d, crawl_mode=%s, since_date=%s, background=%s",
        request.max_jobs_per_group, request.max_pages, request.max_posts_per_page,
        crawl_mode, request.since_date or "자동", request.background,
    )

    if request.background:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            None,
            _run_manual_crawl_sync,
            request.max_jobs_per_group,
            request.max_pages,
            request.max_posts_per_page,
            since_date_dt,
            crawl_mode,
        )
        return JSONResponse(
            status_code=202,
            content={
                "message": "크롤링이 백그라운드에서 시작되었습니다. 진행 상황은 상태 새로고침으로 확인하세요.",
                "crawled": 0,
                "upserted": 0,
                "skipped": 0,
                "errors": 0,
                "elapsed_seconds": 0.0,
            },
        )

    set_crawl_running(True)
    set_crawl_progress(0, 0)
    try:
        pipeline = CrawlPipeline()
        result = await pipeline.run(
            max_jobs_per_group=request.max_jobs_per_group,
            max_pages=request.max_pages,
            max_posts_per_page=request.max_posts_per_page,
            since_date=since_date_dt,
            crawl_mode=crawl_mode,
            progress_callback=set_crawl_progress,
        )
        _push_crawl_history("manual", datetime.now(timezone.utc), result)
        return CrawlTriggerResponse(
            message="크롤링 완료",
            crawled=result.crawled,
            upserted=result.upserted,
            skipped=result.skipped,
            errors=result.errors,
            elapsed_seconds=round(result.elapsed_seconds, 1),
        )
    except Exception as e:
        logger.exception("수동 크롤링 실패: %s", e)
        raise HTTPException(status_code=500, detail=f"크롤링 실패: {str(e)}")
    finally:
        set_crawl_running(False)


@router.get("/crawl/history", response_model=CrawlHistoryResponse)
async def crawl_history():
    """최근 크롤링 이력 (최신순)."""
    return CrawlHistoryResponse(history=get_crawl_history())


@router.get("/users/count")
def admin_user_count(db: Session = Depends(get_db)):
    """관리자용: 가입 회원 수."""
    return {"count": db.query(User).count()}


@router.get("/users")
def admin_list_users(db: Session = Depends(get_db)):
    """관리자용: 회원 목록 (id, email, 본캐)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "main_character_name": u.main_character_name,
        }
        for u in users
    ]


@router.get("/sessions")
def admin_list_sessions(
    db: Session = Depends(get_db),
    user_id: str | None = Query(None, description="user_id 필터. __anonymous__면 익명만"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """관리자용: 세션 목록 (최신순). user_id로 사용자별 필터 가능."""
    q = db.query(ChatSession).order_by(ChatSession.updated_at.desc())
    if user_id is not None:
        if user_id == "__anonymous__":
            q = q.filter(ChatSession.user_id.is_(None))
        else:
            import uuid as _uuid
            try:
                uid = _uuid.UUID(user_id)
                q = q.filter(ChatSession.user_id == uid)
            except ValueError:
                pass  # 잘못된 UUID면 필터 없이 진행
    sessions = q.offset(offset).limit(limit).all()
    result = []
    for s in sessions:
        result.append({
            "id": str(s.id),
            "title": s.title,
            "user_id": str(s.user_id) if s.user_id else None,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "message_count": len(s.messages),
        })
    return result


@router.get("/sessions/{session_id}")
def admin_get_session(session_id: str, db: Session = Depends(get_db)):
    """관리자용: 세션 상세 (메시지 포함) 조회."""
    import uuid as _uuid
    try:
        sid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 세션 ID")
    session = db.query(ChatSession).filter(ChatSession.id == sid).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    messages = [
        {"role": m.role, "content": m.content, "references": m.references}
        for m in session.messages
    ]
    return {
        "id": str(session.id),
        "title": session.title,
        "user_id": str(session.user_id) if session.user_id else None,
        "messages": messages,
    }


@router.delete("/sessions/{session_id}")
def admin_delete_session(session_id: str, db: Session = Depends(get_db)):
    """관리자용: 세션 삭제."""
    import uuid as _uuid
    try:
        sid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 세션 ID")
    session = db.query(ChatSession).filter(ChatSession.id == sid).first()
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    db.delete(session)
    db.commit()
    return {"status": "ok"}


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
