"""OpenAI API 래퍼 (임베딩 + 채팅 + Function Calling). 지수 백오프 재시도 및 토큰 비용 로깅 포함."""
import json
import logging
import time
from typing import Any, Callable, Generator

from openai import APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


def _with_retry(fn, *args, **kwargs):
    """지수 백오프로 최대 _MAX_RETRIES회 재시도. RateLimit/Timeout/5xx에만 재시도."""
    for attempt in range(_MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except (RateLimitError, APITimeoutError) as e:
            if attempt == _MAX_RETRIES - 1:
                raise
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(
                "OpenAI API 호출 실패 (%s), %.1f초 후 재시도 (%d/%d)",
                type(e).__name__, delay, attempt + 1, _MAX_RETRIES,
            )
            time.sleep(delay)
        except APIStatusError as e:
            if e.status_code >= 500:
                if attempt == _MAX_RETRIES - 1:
                    raise
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "OpenAI 서버 오류 (%d), %.1f초 후 재시도 (%d/%d)",
                    e.status_code, delay, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(delay)
            else:
                raise


class OpenAIClient:
    """OpenAI API 클라이언트 래퍼."""

    def __init__(self, api_key: str | None = None):
        self.client = OpenAI(api_key=api_key or settings.openai_api_key)
        self.embedding_model = settings.openai_embedding_model
        self.chat_model = settings.openai_chat_model

    # ── 임베딩 ──────────────────────────────────────────

    def create_embedding(self, text: str) -> list[float]:
        """단일 텍스트의 임베딩 벡터 생성."""
        def _call():
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text,
            )
            logger.debug("임베딩 토큰: %d", response.usage.total_tokens)
            return response.data[0].embedding

        return _with_retry(_call)

    def create_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 임베딩 생성 (최대 2048개)."""
        def _call():
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=texts,
            )
            # text-embedding-3-small: $0.02/1M tokens
            cost = response.usage.total_tokens * 2e-8
            logger.info(
                "배치 임베딩 토큰: %d (약 $%.5f)",
                response.usage.total_tokens, cost,
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

        return _with_retry(_call)

    # ── 채팅 ────────────────────────────────────────────

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        """채팅 완성 (답변 생성)."""
        def _call():
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                max_tokens=max_tokens or settings.rag_max_tokens,
                temperature=temperature,
            )
            u = response.usage
            # gpt-4o-mini: input $0.15/1M, output $0.60/1M
            cost = u.prompt_tokens * 1.5e-7 + u.completion_tokens * 6e-7
            logger.info(
                "채팅 토큰: prompt=%d, completion=%d (약 $%.5f)",
                u.prompt_tokens, u.completion_tokens, cost,
            )
            return response.choices[0].message.content

        return _with_retry(_call)

    def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> Generator[str, None, None]:
        """스트리밍 채팅 완성 (제너레이터)."""
        def _create():
            return self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                max_tokens=max_tokens or settings.rag_max_tokens,
                temperature=temperature,
                stream=True,
            )

        stream = _with_retry(_create)
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Callable[[str, dict], Any],
        max_turns: int = 5,
        temperature: float = 0.1,
    ) -> str:
        """OpenAI Function Calling 루프: 도구 호출이 끝날 때까지 반복 실행.

        Args:
            messages: 초기 메시지 목록
            tools: OpenAI tools 형식 스키마 정의
            tool_executor: (tool_name, args) → result 실행 함수
            max_turns: 최대 도구 호출 반복 횟수
        Returns:
            LLM의 최종 텍스트 응답
        """
        msgs = list(messages)
        last_content = ""

        for _ in range(max_turns):
            def _call():
                return self.client.chat.completions.create(
                    model=self.chat_model,
                    messages=msgs,
                    tools=tools,
                    tool_choice="auto",
                    temperature=temperature,
                    max_tokens=settings.rag_max_tokens,
                )

            response = _with_retry(_call)
            choice = response.choices[0]

            u = response.usage
            cost = u.prompt_tokens * 1.5e-7 + u.completion_tokens * 6e-7
            logger.info(
                "Function Calling 토큰: prompt=%d, completion=%d (약 $%.5f)",
                u.prompt_tokens, u.completion_tokens, cost,
            )

            last_content = choice.message.content or ""

            # 도구 호출 없으면 최종 답변 반환
            if not choice.message.tool_calls:
                return last_content

            # 어시스턴트 메시지 추가 (tool_calls 포함)
            msgs.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ],
            })

            # 각 도구 실행 결과 추가
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                    result = tool_executor(tc.function.name, args)
                    tool_result = json.dumps(result, ensure_ascii=False)
                except Exception as e:
                    logger.warning("도구 실행 오류 [%s]: %s", tc.function.name, e)
                    tool_result = json.dumps({"error": str(e)}, ensure_ascii=False)

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        return last_content
