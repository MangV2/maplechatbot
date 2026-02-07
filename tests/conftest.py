"""테스트 공통 fixtures."""
import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI 클라이언트."""
    client = MagicMock()
    client.create_embedding.return_value = [0.1] * 1536
    client.create_embeddings_batch.return_value = [[0.1] * 1536]
    client.chat_completion.return_value = "테스트 답변입니다."
    return client


@pytest.fixture
def mock_qdrant_store():
    """Mock Qdrant 저장소."""
    store = MagicMock()
    store.collection_name = "test_maple_posts"
    store.count.return_value = 100
    store.search.return_value = [
        {
            "id": 1,
            "score": 0.95,
            "직업": "아크",
            "직업군": "전사",
            "제목": "아크 스킬 트리 가이드",
            "작성일": "2025-01-01",
            "본문": "아크 스킬 트리 관련 내용입니다.",
            "댓글": "좋은 정보 감사합니다|도움이 됐어요",
        },
        {
            "id": 2,
            "score": 0.85,
            "직업": "아크",
            "직업군": "전사",
            "제목": "아크 보스 세팅",
            "작성일": "2025-01-02",
            "본문": "보스 레이드 시 아크 세팅법입니다.",
            "댓글": "",
        },
    ]
    return store


@pytest.fixture
def sample_job_list():
    """샘플 직업 목록."""
    return ["아크", "제로", "히어로", "아델", "카인", "라라", "칼리", "은월", "미하일"]
