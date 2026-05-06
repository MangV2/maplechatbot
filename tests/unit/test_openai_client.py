"""OpenAI 클라이언트 단위 테스트."""
from unittest.mock import MagicMock, patch

import pytest


class TestOpenAIClientEmbedding:
    """임베딩 생성 테스트."""

    @patch("app.rag.openai_client.OpenAI")
    def test_create_embedding_returns_vector(self, mock_openai_cls):
        """단일 임베딩 생성 시 1536차원 벡터 반환."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
        mock_client.embeddings.create.return_value = mock_response

        from app.rag.openai_client import OpenAIClient

        client = OpenAIClient(api_key="test-key")
        result = client.create_embedding("테스트 텍스트")

        assert len(result) == 1536
        mock_client.embeddings.create.assert_called_once()

    @patch("app.rag.openai_client.OpenAI")
    def test_create_embeddings_batch_returns_multiple(self, mock_openai_cls):
        """배치 임베딩 생성 시 입력 수만큼 벡터 반환."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1] * 1536, index=0),
            MagicMock(embedding=[0.2] * 1536, index=1),
        ]
        mock_client.embeddings.create.return_value = mock_response

        from app.rag.openai_client import OpenAIClient

        client = OpenAIClient(api_key="test-key")
        result = client.create_embeddings_batch(["텍스트1", "텍스트2"])

        assert len(result) == 2
        assert len(result[0]) == 1536
        assert len(result[1]) == 1536


class TestOpenAIClientChat:
    """채팅 완성 테스트."""

    @patch("app.rag.openai_client.OpenAI")
    def test_chat_completion_returns_string(self, mock_openai_cls):
        """채팅 완성 시 문자열 답변 반환."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="테스트 답변"))]
        mock_client.chat.completions.create.return_value = mock_response

        from app.rag.openai_client import OpenAIClient

        client = OpenAIClient(api_key="test-key")
        result = client.chat_completion(
            messages=[{"role": "user", "content": "질문"}]
        )

        assert result == "테스트 답변"
        mock_client.chat.completions.create.assert_called_once()

    @patch("app.rag.openai_client.OpenAI")
    def test_chat_completion_passes_parameters(self, mock_openai_cls):
        """채팅 완성 시 온도, max_tokens 파라미터 전달."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="답변"))]
        mock_client.chat.completions.create.return_value = mock_response

        from app.rag.openai_client import OpenAIClient

        client = OpenAIClient(api_key="test-key")
        client.chat_completion(
            messages=[{"role": "user", "content": "질문"}],
            max_tokens=100,
            temperature=0.3,
        )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["temperature"] == 0.3

    @patch("app.rag.openai_client.OpenAI")
    def test_chat_completion_stream_yields_chunks(self, mock_openai_cls):
        """스트리밍 시 청크 단위로 yield."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        chunk1 = MagicMock()
        chunk1.choices = [MagicMock(delta=MagicMock(content="안녕"))]
        chunk2 = MagicMock()
        chunk2.choices = [MagicMock(delta=MagicMock(content="하세요"))]
        chunk3 = MagicMock()
        chunk3.choices = [MagicMock(delta=MagicMock(content=None))]

        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])

        from app.rag.openai_client import OpenAIClient

        client = OpenAIClient(api_key="test-key")
        chunks = list(
            client.chat_completion_stream(
                messages=[{"role": "user", "content": "질문"}]
            )
        )

        assert chunks == ["안녕", "하세요"]
