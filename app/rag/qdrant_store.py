"""Qdrant 벡터 DB 클라이언트 래퍼."""
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.config import settings

logger = logging.getLogger(__name__)


class QdrantStore:
    """Qdrant 벡터 저장소 래퍼."""

    VECTOR_SIZE = 1536  # OpenAI text-embedding-3-small

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        collection_name: str | None = None,
        in_memory: bool = False,
    ):
        if in_memory:
            self.client = QdrantClient(location=":memory:")
        else:
            self.client = QdrantClient(
                host=host or settings.qdrant_host,
                port=port or settings.qdrant_port,
            )
        self.collection_name = collection_name or settings.qdrant_collection
        self._ensure_collection()

    # ── 컬렉션 관리 ────────────────────────────────────

    def _ensure_collection(self):
        """컬렉션이 없으면 생성."""
        collections = self.client.get_collections().collections
        if not any(c.name == self.collection_name for c in collections):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Qdrant 컬렉션 '%s' 생성 완료", self.collection_name)

    def delete_collection(self):
        """컬렉션 삭제."""
        self.client.delete_collection(self.collection_name)
        logger.info("Qdrant 컬렉션 '%s' 삭제 완료", self.collection_name)

    # ── 데이터 적재 ────────────────────────────────────

    def upsert(self, point_id: int | str, vector: list[float], payload: dict[str, Any]):
        """단일 문서 upsert."""
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(id=point_id, vector=vector, payload=payload)
            ],
        )

    def upsert_batch(
        self,
        ids: list[int | str],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]],
        batch_size: int = 100,
    ):
        """배치 upsert."""
        total = len(ids)
        for i in range(0, total, batch_size):
            batch_end = min(i + batch_size, total)
            points = [
                PointStruct(id=ids[j], vector=vectors[j], payload=payloads[j])
                for j in range(i, batch_end)
            ]
            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )
            logger.info("Qdrant upsert 진행: %d/%d", batch_end, total)

    # ── 검색 ───────────────────────────────────────────

    def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        filter_job: str | None = None,
        filter_group: str | None = None,
    ) -> list[dict[str, Any]]:
        """유사도 검색. filter_job(직업) 또는 filter_group(직업군) 필터 적용."""
        conditions = []
        if filter_job:
            conditions.append(
                FieldCondition(key="직업", match=MatchValue(value=filter_job))
            )
        if filter_group:
            conditions.append(
                FieldCondition(key="직업군", match=MatchValue(value=filter_group))
            )

        search_filter = Filter(must=conditions) if conditions else None

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=search_filter,
        )

        return [
            {"id": hit.id, "score": hit.score, **hit.payload}
            for hit in response.points
        ]

    # ── 유틸 ───────────────────────────────────────────

    def count(self) -> int:
        """컬렉션 내 포인트 수 반환."""
        info = self.client.get_collection(self.collection_name)
        return info.points_count

    def get_unique_jobs(self) -> list[str]:
        """컬렉션에서 고유 직업 목록 추출."""
        all_jobs: set[str] = set()
        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=100,
                offset=offset,
                with_payload=["직업"],
            )
            for point in results:
                job = point.payload.get("직업")
                if job:
                    all_jobs.add(job)
            if offset is None:
                break
        return sorted(all_jobs)

    def get_job_stats(self) -> dict[str, Any]:
        """직업/직업군별 개수 및 전체 포인트 수."""
        info = self.client.get_collection(self.collection_name)
        jobs: Counter = Counter()
        groups: Counter = Counter()
        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=100,
                offset=offset,
                with_payload=["직업", "직업군"],
            )
            for point in results:
                job = point.payload.get("직업")
                group = point.payload.get("직업군")
                if job:
                    jobs[job] += 1
                if group:
                    groups[group] += 1
            if offset is None:
                break
        return {
            "points_count": info.points_count,
            "jobs": dict(jobs.most_common()),
            "groups": dict(groups.most_common()),
        }

    def scroll_documents(
        self,
        limit: int = 20,
        offset: int | None = None,
        job: str | None = None,
        job_group: str | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        """필터 조건으로 문서 목록 스크롤. (items, next_offset) 반환."""
        conditions = []
        if job:
            conditions.append(
                FieldCondition(key="직업", match=MatchValue(value=job))
            )
        if job_group:
            conditions.append(
                FieldCondition(key="직업군", match=MatchValue(value=job_group))
            )
        scroll_filter = Filter(must=conditions) if conditions else None
        results, next_offset = self.client.scroll(
            collection_name=self.collection_name,
            limit=limit,
            offset=offset,
            scroll_filter=scroll_filter,
            with_payload=True,
            with_vectors=False,
        )
        items = [{"id": pt.id, **pt.payload} for pt in results]
        return items, next_offset

    def get_max_written_date(self) -> datetime | None:
        """Qdrant에 저장된 게시물 중 가장 최근 작성일 반환."""
        from app.crawler.date_utils import parse_post_date

        max_date: datetime | None = None
        offset = None
        while True:
            results, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in results:
                payload = point.payload or {}
                # 작성일 키 우선, 없으면 payload 값 중 날짜 형태인 것 시도
                written_date_str = payload.get("작성일") or payload.get("date") or payload.get("작성일시")
                if written_date_str:
                    d = parse_post_date(str(written_date_str))
                    if d:
                        if max_date is None or d > max_date:
                            max_date = d
                        continue
                # 키로 못 찾은 경우 값이 날짜 형태인 항목 탐색
                for v in payload.values():
                    if v and isinstance(v, str) and re.match(r"\d{4}[.-]\d", v.strip()):
                        d = parse_post_date(v)
                        if d:
                            if max_date is None or d > max_date:
                                max_date = d
                            break
            if offset is None:
                break
        return max_date
