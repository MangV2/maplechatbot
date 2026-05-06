"""Qdrant 저장소 단위 테스트."""
from unittest.mock import MagicMock, patch


class TestQdrantStoreCollection:
    """컬렉션 관리 테스트."""

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_creates_collection_if_not_exists(self, mock_client_cls):
        """컬렉션이 없으면 새로 생성."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])

        from app.rag.qdrant_store import QdrantStore

        QdrantStore(host="localhost", port=6333, collection_name="test_col")

        mock_client.create_collection.assert_called_once()

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_skips_creation_if_collection_exists(self, mock_client_cls):
        """컬렉션이 이미 있으면 생성하지 않음."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        existing = MagicMock()
        existing.name = "test_col"
        mock_client.get_collections.return_value = MagicMock(collections=[existing])

        from app.rag.qdrant_store import QdrantStore

        QdrantStore(host="localhost", port=6333, collection_name="test_col")

        mock_client.create_collection.assert_not_called()


class TestQdrantStoreSearch:
    """검색 테스트."""

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_search_returns_results(self, mock_client_cls):
        """필터 없는 검색 시 결과 반환."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])

        mock_hit = MagicMock()
        mock_hit.id = 1
        mock_hit.score = 0.95
        mock_hit.payload = {"직업": "아크", "제목": "테스트 게시글"}
        mock_client.search.return_value = [mock_hit]

        from app.rag.qdrant_store import QdrantStore

        store = QdrantStore(host="localhost", port=6333, collection_name="test_col")
        results = store.search([0.1] * 1536, top_k=5)

        assert len(results) == 1
        assert results[0]["직업"] == "아크"
        assert results[0]["score"] == 0.95
        assert results[0]["id"] == 1

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_search_with_job_filter_applies_filter(self, mock_client_cls):
        """직업 필터 지정 시 필터 조건이 적용됨."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.search.return_value = []

        from app.rag.qdrant_store import QdrantStore

        store = QdrantStore(host="localhost", port=6333, collection_name="test_col")
        store.search([0.1] * 1536, top_k=5, filter_job="아크")

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["query_filter"] is not None

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_search_without_filter_has_no_filter(self, mock_client_cls):
        """필터 미지정 시 필터 조건 없음."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.search.return_value = []

        from app.rag.qdrant_store import QdrantStore

        store = QdrantStore(host="localhost", port=6333, collection_name="test_col")
        store.search([0.1] * 1536, top_k=5)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["query_filter"] is None


class TestQdrantStoreUpsert:
    """데이터 적재 테스트."""

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_upsert_single_document(self, mock_client_cls):
        """단일 문서 upsert 호출."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])

        from app.rag.qdrant_store import QdrantStore

        store = QdrantStore(host="localhost", port=6333, collection_name="test_col")
        store.upsert(1, [0.1] * 1536, {"직업": "아크"})

        mock_client.upsert.assert_called_once()

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_upsert_batch_processes_all(self, mock_client_cls):
        """배치 upsert가 전체 데이터를 처리."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])

        from app.rag.qdrant_store import QdrantStore

        store = QdrantStore(host="localhost", port=6333, collection_name="test_col")

        ids = list(range(5))
        vectors = [[0.1] * 1536] * 5
        payloads = [{"직업": f"직업{i}"} for i in range(5)]

        store.upsert_batch(ids, vectors, payloads, batch_size=2)

        # 5개를 배치 2로 나누면 3번 호출
        assert mock_client.upsert.call_count == 3


class TestQdrantStoreUtils:
    """유틸리티 테스트."""

    @patch("app.rag.qdrant_store.QdrantClient")
    def test_count_returns_points_count(self, mock_client_cls):
        """포인트 수 정확히 반환."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_client.get_collection.return_value = MagicMock(points_count=42)

        from app.rag.qdrant_store import QdrantStore

        store = QdrantStore(host="localhost", port=6333, collection_name="test_col")

        assert store.count() == 42
