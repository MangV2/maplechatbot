"""크롤링 → 임베딩 → Qdrant 적재 파이프라인."""
import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.crawler.date_utils import parse_post_date
from app.crawler.inven_crawler import CrawlResult, CrawledPost, InvenCrawler
from app.rag.openai_client import OpenAIClient
from app.rag.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

# 마지막 크롤링 날짜 저장 파일 경로
LAST_CRAWL_DATE_FILE = Path("data/last_crawl_date.txt")


def filter_posts_by_since(posts: list[CrawledPost], since_date: datetime) -> list[CrawledPost]:
    """작성일이 since_date 이상인 게시글만 반환. 파싱 실패한 글은 제외(날짜 기준 수집 시)."""
    since_date = since_date if since_date.tzinfo else since_date.replace(tzinfo=timezone.utc)
    out = []
    for p in posts:
        d = parse_post_date(p.작성일)
        if d is None:
            continue
        if d >= since_date:
            out.append(p)
    return out


def get_max_written_date_from_posts(posts: list[CrawledPost]) -> datetime | None:
    """게시글 목록에서 가장 최근 작성일 반환."""
    dates = []
    for p in posts:
        d = parse_post_date(p.작성일)
        if d:
            dates.append(d)
    return max(dates) if dates else None


def load_last_crawl_date() -> datetime | None:
    """저장된 마지막 크롤링 날짜 로드."""
    if not LAST_CRAWL_DATE_FILE.exists():
        return None
    try:
        content = LAST_CRAWL_DATE_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return None
        # ISO 형식 또는 YYYY-MM-DD 형식 파싱
        try:
            dt = datetime.fromisoformat(content.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            # YYYY-MM-DD 형식 시도
            dt = datetime.strptime(content, "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
    except Exception as e:
        logger.warning("마지막 크롤링 날짜 로드 실패: %s", e)
        return None


def save_last_crawl_date(date: datetime):
    """마지막 크롤링 날짜 저장."""
    try:
        LAST_CRAWL_DATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # ISO 형식으로 저장 (UTC)
        date_utc = date if date.tzinfo else date.replace(tzinfo=timezone.utc)
        LAST_CRAWL_DATE_FILE.write_text(date_utc.isoformat(), encoding="utf-8")
        logger.info("마지막 크롤링 날짜 저장: %s", date_utc.isoformat())
    except Exception as e:
        logger.error("마지막 크롤링 날짜 저장 실패: %s", e)


def determine_since_date(store: QdrantStore) -> datetime | None:
    """자동으로 since_date 결정: 1) 저장된 날짜 → 2) Qdrant 최신 작성일 → 3) None."""
    # 1순위: 저장된 마지막 크롤링 날짜
    last_date = load_last_crawl_date()
    if last_date:
        logger.info("저장된 마지막 크롤링 날짜 사용: %s", last_date.isoformat())
        return last_date

    # 2순위: Qdrant에서 가장 최근 작성일
    try:
        max_date = store.get_max_written_date()
        if max_date:
            logger.info("Qdrant 최신 작성일 사용: %s", max_date.isoformat())
            return max_date
    except Exception as e:
        logger.warning("Qdrant 최신 작성일 조회 실패: %s", e)

    # 3순위: 없음 (전체 수집)
    logger.info("since_date 자동 결정 실패 → 전체 수집")
    return None


@dataclass
class PipelineResult:
    """파이프라인 실행 결과."""

    crawled: int = 0
    embedded: int = 0
    upserted: int = 0
    skipped: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0


def _generate_point_id(post: CrawledPost) -> str:
    """게시글에서 Qdrant point ID 생성 (SHA256 해시 앞 16자리 hex → int)."""
    unique_key = f"{post.직업군}:{post.직업}:{post.post_id or post.제목}"
    hash_hex = hashlib.sha256(unique_key.encode()).hexdigest()[:16]
    # Qdrant unsigned int64 범위 내로 변환
    return int(hash_hex, 16) % (2**63)


def _post_to_embedding_text(post: CrawledPost) -> str:
    """임베딩 생성용 텍스트 구성."""
    return f"직업: {post.직업} | 제목: {post.제목} | {post.본문[:2000]}"


def _post_to_payload(post: CrawledPost) -> dict:
    """Qdrant 페이로드 구성."""
    return {
        "직업": post.직업,
        "직업군": post.직업군,
        "제목": post.제목,
        "본문": post.본문,
        "댓글": post.댓글,
        "작성일": post.작성일,
        "link": post.link,
        "post_id": post.post_id,
    }


class CrawlPipeline:
    """크롤링 → 임베딩 → Qdrant 적재 파이프라인."""

    def __init__(
        self,
        crawler: InvenCrawler | None = None,
        openai_client: OpenAIClient | None = None,
        qdrant_store: QdrantStore | None = None,
        embedding_batch_size: int = 50,
    ):
        self.crawler = crawler or InvenCrawler()
        self.ai = openai_client or OpenAIClient()
        self.store = qdrant_store or QdrantStore()
        self.embedding_batch_size = embedding_batch_size

    # ── 임베딩 & 적재 ─────────────────────────────────

    def embed_and_upsert(self, posts: list[CrawledPost]) -> PipelineResult:
        """게시글 목록을 임베딩 → Qdrant 적재."""
        result = PipelineResult()
        total = len(posts)

        if not posts:
            logger.info("적재할 게시글이 없습니다.")
            return result

        logger.info("임베딩 & 적재 시작: %d건", total)
        start = time.time()

        for i in range(0, total, self.embedding_batch_size):
            batch = posts[i : i + self.embedding_batch_size]
            batch_end = min(i + self.embedding_batch_size, total)

            try:
                # 임베딩 텍스트 생성
                texts = [_post_to_embedding_text(p) for p in batch]

                # 임베딩 생성
                vectors = self.ai.create_embeddings_batch(texts)
                result.embedded += len(vectors)

                # Qdrant 적재
                ids = [_generate_point_id(p) for p in batch]
                payloads = [_post_to_payload(p) for p in batch]

                self.store.upsert_batch(
                    ids, vectors, payloads,
                    batch_size=self.embedding_batch_size,
                )
                result.upserted += len(batch)

                logger.info(
                    "적재 진행: %d/%d (%.1f%%)",
                    batch_end, total, batch_end / total * 100,
                )

                # Rate limit 대비
                time.sleep(0.5)

            except Exception as e:
                result.errors += len(batch)
                logger.error("배치 %d-%d 적재 실패: %s", i, batch_end, e)
                time.sleep(2)

        result.elapsed_seconds = time.time() - start
        logger.info(
            "적재 완료 — 임베딩: %d, 적재: %d, 에러: %d, 소요: %.1f초",
            result.embedded, result.upserted, result.errors, result.elapsed_seconds,
        )
        return result

    # ── 전체 파이프라인 ────────────────────────────────

    async def run(
        self,
        since_date: datetime | None = None,
        crawl_mode: str = "all",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> PipelineResult:
        """크롤링 → (날짜 필터) → 임베딩 → Qdrant 적재.

        Args:
            since_date: 이 값이 있으면 해당 날짜 이후 작성글만 수집.
                       None이면 자동 결정 (저장된 날짜 → Qdrant 최신 작성일 → 전체 수집)
            crawl_mode: "job_only" 직업게시판만, "flat_only" 단일게시판만, "all" 전체
            progress_callback: (완료된 직업/게시판 수, 전체 수) 진행 상황 콜백
        """
        logger.info("=== 파이프라인 시작 ===")
        start = time.time()

        # 1) since_date 자동 결정 (None인 경우)
        if since_date is None:
            since_date = determine_since_date(self.store)
            if since_date:
                logger.info("자동 결정된 수집 시작일: %s", since_date.isoformat())

        # 2) 크롤링 (since_date 있으면 직업/게시판별로 이전 글 나오면 즉시 중단)
        include_job = crawl_mode in ("job_only", "all")
        include_flat = crawl_mode in ("flat_only", "all")
        crawl_result: CrawlResult = await self.crawler.crawl(
            since_date=since_date,
            include_job_boards=include_job,
            include_flat_boards=include_flat,
            parse_post_date=parse_post_date,
            progress_callback=progress_callback,
        )

        if not crawl_result.posts:
            logger.warning("크롤링 결과가 없습니다.")
            return PipelineResult(errors=crawl_result.errors)

        # 3) 날짜 기준 필터 (메타데이터 활용)
        dropped = 0
        if since_date is not None:
            before = len(crawl_result.posts)
            crawl_result.posts = filter_posts_by_since(crawl_result.posts, since_date)
            dropped = before - len(crawl_result.posts)
            if dropped:
                logger.info("날짜 기준 필터: %d건 제외 (기준: %s)", dropped, since_date.isoformat())

        if not crawl_result.posts:
            logger.warning("날짜 필터 후 수집할 게시글이 없습니다.")
            result = PipelineResult(elapsed_seconds=time.time() - start)
            result.skipped = dropped
            return result

        # 4) 임베딩 & 적재
        pipeline_result = self.embed_and_upsert(crawl_result.posts)
        pipeline_result.crawled = len(crawl_result.posts)
        pipeline_result.elapsed_seconds = time.time() - start
        pipeline_result.skipped = dropped

        # 5) 이번 크롤에서 수집한 게시물 중 가장 최근 작성일 저장
        max_written = get_max_written_date_from_posts(crawl_result.posts)
        if max_written:
            save_last_crawl_date(max_written)
            logger.info("다음 크롤링용 날짜 저장: %s", max_written.isoformat())

        logger.info(
            "=== 파이프라인 완료 === 크롤링: %d → 임베딩: %d → 적재: %d (스킵: %d, 에러: %d, %.1f초)",
            pipeline_result.crawled,
            pipeline_result.embedded,
            pipeline_result.upserted,
            pipeline_result.skipped,
            pipeline_result.errors,
            pipeline_result.elapsed_seconds,
        )
        return pipeline_result

    def run_sync(self, **kwargs) -> PipelineResult:
        """동기 래퍼 (스케줄러에서 호출용)."""
        return asyncio.run(self.run(**kwargs))
