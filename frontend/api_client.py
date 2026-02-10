"""백엔드 API 통신 클라이언트."""
import json
import os
from typing import Generator

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 30.0


# ── 채팅 API ───────────────────────────────────────────


def chat(query: str, top_k: int = 5, use_cot: bool = True) -> dict:
    """동기 채팅 API 호출."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{API_BASE_URL}/chat",
            json={"query": query, "top_k": top_k, "use_cot": use_cot},
        )
        response.raise_for_status()
        return response.json()


def chat_stream(
    query: str, top_k: int = 5, use_cot: bool = True
) -> Generator[dict, None, None]:
    """SSE 스트리밍 채팅 API 호출."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        with client.stream(
            "POST",
            f"{API_BASE_URL}/chat/stream",
            json={"query": query, "top_k": top_k, "use_cot": use_cot},
        ) as response:
            response.raise_for_status()
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event, buffer = buffer.split("\n\n", 1)
                    event = event.strip()
                    if event.startswith("data: "):
                        data = event[6:]
                        if data == "[DONE]":
                            return
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue


# ── 세션 API ──────────────────────────────────────────


def list_sessions() -> list[dict]:
    """세션 목록 조회."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{API_BASE_URL}/sessions")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return []


def create_session() -> dict:
    """새 세션 생성."""
    with httpx.Client(timeout=5.0) as client:
        resp = client.post(f"{API_BASE_URL}/sessions")
        resp.raise_for_status()
        return resp.json()


def get_session(session_id: str) -> dict | None:
    """세션 상세 (메시지 포함) 조회."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{API_BASE_URL}/sessions/{session_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def save_message(session_id: str, role: str, content: str, references: list | None = None):
    """세션에 메시지 저장."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{API_BASE_URL}/sessions/{session_id}/messages",
                json={"role": role, "content": content, "references": references},
            )
            resp.raise_for_status()
    except Exception:
        pass  # 저장 실패해도 UI는 계속 동작


def delete_session(session_id: str):
    """세션 삭제."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.delete(f"{API_BASE_URL}/sessions/{session_id}")
            resp.raise_for_status()
    except Exception:
        pass


# ── 헬스체크 ──────────────────────────────────────────


def health_check() -> dict:
    """헬스 체크."""
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{API_BASE_URL}/health")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        return {"status": "error", "qdrant_status": str(e), "document_count": 0}
