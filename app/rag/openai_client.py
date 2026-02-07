"""OpenAI API 래퍼 (임베딩 + 채팅)."""
import logging
from typing import Generator

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


class OpenAIClient:
    """OpenAI API 클라이언트 래퍼."""

    def __init__(self, api_key: str | None = None):
        self.client = OpenAI(api_key=api_key or settings.openai_api_key)
        self.embedding_model = settings.openai_embedding_model
        self.chat_model = settings.openai_chat_model

    # ── 임베딩 ──────────────────────────────────────────

    def create_embedding(self, text: str) -> list[float]:
        """단일 텍스트의 임베딩 벡터 생성."""
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    def create_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩 생성 (최대 2048개)."""
        response = self.client.embeddings.create(
            model=self.embedding_model,
            input=texts,
        )
        # API 응답은 index 순서 보장 안 될 수 있으므로 정렬
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    # ── 채팅 ────────────────────────────────────────────

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        """채팅 완성 (답변 생성)."""
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            max_tokens=max_tokens or settings.rag_max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content

    def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """스트리밍 채팅 완성 (제너레이터)."""
        stream = self.client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            max_tokens=max_tokens or settings.rag_max_tokens,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
