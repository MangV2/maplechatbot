"""크롤링 → 임베딩 → Qdrant 적재 파이프라인."""
import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field

from app.crawler.inven_crawler import CrawlResult, CrawledPost, InvenCrawler
from app.rag.openai_client import OpenAIClient
from app.rag.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)


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
    return f"직업: {post.직업} | 제목: {post.제목} | {post.본문[:500]}"


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
        max_jobs_per_group: int | None = None,
        max_pages: int = 1,
        max_posts_per_page: int = 20,
    ) -> PipelineResult:
        """크롤링 → 임베딩 → Qdrant 적재 전체 파이프라인.

        Args:
            max_jobs_per_group: 직업군당 수집할 최대 직업 수
            max_pages: 직업별 수집할 페이지 수
            max_posts_per_page: 페이지당 수집할 최대 게시글 수
        """
        logger.info("=== 파이프라인 시작 ===")
        start = time.time()

        # 1) 크롤링
        crawl_result: CrawlResult = await self.crawler.crawl(
            max_jobs_per_group=max_jobs_per_group,
            max_pages=max_pages,
            max_posts_per_page=max_posts_per_page,
        )

        if not crawl_result.posts:
            logger.warning("크롤링 결과가 없습니다.")
            return PipelineResult(errors=crawl_result.errors)

        # 2) 임베딩 & 적재
        pipeline_result = self.embed_and_upsert(crawl_result.posts)
        pipeline_result.crawled = len(crawl_result.posts)
        pipeline_result.elapsed_seconds = time.time() - start

        logger.info(
            "=== 파이프라인 완료 === 크롤링: %d → 임베딩: %d → 적재: %d (에러: %d, %.1f초)",
            pipeline_result.crawled,
            pipeline_result.embedded,
            pipeline_result.upserted,
            pipeline_result.errors,
            pipeline_result.elapsed_seconds,
        )
        return pipeline_result

    def run_sync(self, **kwargs) -> PipelineResult:
        """동기 래퍼 (스케줄러에서 호출용)."""
        return asyncio.run(self.run(**kwargs))
