"""데이터 적재 파이프라인 단위 테스트."""
import pytest
from unittest.mock import MagicMock

from app.crawler.inven_crawler import CrawledPost
from app.crawler.pipeline import (
    CrawlPipeline,
    PipelineResult,
    _generate_point_id,
    _post_to_embedding_text,
    _post_to_payload,
)


def _make_post(**kwargs) -> CrawledPost:
    """테스트용 CrawledPost 팩토리."""
    defaults = {
        "직업군": "전사",
        "직업": "아크",
        "제목": "테스트 제목",
        "본문": "테스트 본문 내용입니다.",
        "댓글": "댓글1 | 댓글2",
        "작성일": "2025-01-01",
        "link": "https://inven.co.kr/board/maple/2294/12345",
        "post_id": "12345",
    }
    defaults.update(kwargs)
    return CrawledPost(**defaults)


class TestPointIdGeneration:
    """Point ID 생성 테스트."""

    def test_same_post_same_id(self):
        """동일 게시글은 동일 ID 생성."""
        post = _make_post()
        id1 = _generate_point_id(post)
        id2 = _generate_point_id(post)
        assert id1 == id2

    def test_different_posts_different_ids(self):
        """다른 게시글은 다른 ID 생성."""
        post1 = _make_post(post_id="111")
        post2 = _make_post(post_id="222")
        assert _generate_point_id(post1) != _generate_point_id(post2)

    def test_id_is_positive_integer(self):
        """ID가 양의 정수."""
        post = _make_post()
        point_id = _generate_point_id(post)
        assert isinstance(point_id, int)
        assert point_id >= 0


class TestPostConversion:
    """게시글 → 임베딩 텍스트/페이로드 변환 테스트."""

    def test_embedding_text_includes_job_and_title(self):
        """임베딩 텍스트에 직업과 제목이 포함."""
        post = _make_post(직업="아크", 제목="아크 가이드")
        text = _post_to_embedding_text(post)
        assert "아크" in text
        assert "아크 가이드" in text

    def test_embedding_text_truncates_body(self):
        """본문이 500자로 잘림."""
        long_body = "가" * 1000
        post = _make_post(본문=long_body)
        text = _post_to_embedding_text(post)
        # "직업: ... | 제목: ... | " 프리픽스 + 500자
        assert len(text) < 600

    def test_payload_has_all_fields(self):
        """페이로드에 필수 필드 모두 포함."""
        post = _make_post()
        payload = _post_to_payload(post)
        assert "직업" in payload
        assert "직업군" in payload
        assert "제목" in payload
        assert "본문" in payload
        assert "댓글" in payload
        assert "작성일" in payload
        assert "link" in payload
        assert "post_id" in payload


class TestCrawlPipelineEmbedAndUpsert:
    """임베딩 & 적재 테스트."""

    def test_embed_and_upsert_processes_all(self):
        """모든 게시글이 임베딩 → 적재됨."""
        mock_ai = MagicMock()
        mock_ai.create_embeddings_batch.return_value = [[0.1] * 1536] * 3
        mock_store = MagicMock()

        pipeline = CrawlPipeline(
            openai_client=mock_ai,
            qdrant_store=mock_store,
            embedding_batch_size=10,
        )

        posts = [_make_post(post_id=str(i)) for i in range(3)]
        result = pipeline.embed_and_upsert(posts)

        assert result.embedded == 3
        assert result.upserted == 3
        assert result.errors == 0
        mock_ai.create_embeddings_batch.assert_called_once()

    def test_embed_and_upsert_empty_list(self):
        """빈 목록 시 아무것도 안 함."""
        pipeline = CrawlPipeline(
            openai_client=MagicMock(),
            qdrant_store=MagicMock(),
        )
        result = pipeline.embed_and_upsert([])

        assert result.upserted == 0
        assert result.embedded == 0

    def test_embed_and_upsert_handles_error(self):
        """임베딩 실패 시 에러 카운트 증가."""
        mock_ai = MagicMock()
        mock_ai.create_embeddings_batch.side_effect = Exception("API error")
        mock_store = MagicMock()

        pipeline = CrawlPipeline(
            openai_client=mock_ai,
            qdrant_store=mock_store,
            embedding_batch_size=10,
        )

        posts = [_make_post(post_id=str(i)) for i in range(3)]
        result = pipeline.embed_and_upsert(posts)

        assert result.errors == 3
        assert result.upserted == 0

    def test_embed_and_upsert_batches_correctly(self):
        """배치 크기에 따라 나눠서 처리."""
        mock_ai = MagicMock()
        mock_ai.create_embeddings_batch.return_value = [[0.1] * 1536] * 2
        mock_store = MagicMock()

        pipeline = CrawlPipeline(
            openai_client=mock_ai,
            qdrant_store=mock_store,
            embedding_batch_size=2,
        )

        posts = [_make_post(post_id=str(i)) for i in range(5)]
        result = pipeline.embed_and_upsert(posts)

        # 5개를 배치 2로 → 3번 호출 (2+2+1)
        assert mock_ai.create_embeddings_batch.call_count == 3
        assert result.upserted == 5
