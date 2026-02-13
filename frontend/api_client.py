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


def list_sessions(limit: int = 100, offset: int = 0) -> list[dict]:
    """세션 목록 조회 (페이징)."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{API_BASE_URL}/sessions",
                params={"limit": limit, "offset": offset},
            )
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


# ── Admin API ──────────────────────────────────────────


def admin_crawl_status() -> dict:
    """크롤링 상태 조회."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{API_BASE_URL}/admin/crawl/status")
        resp.raise_for_status()
        return resp.json()


def admin_suggested_since_date() -> str | None:
    """수집 시작일 자동 제안 (마지막 크롤 날짜 → Qdrant 최신 문서 날짜). 없으면 None."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{API_BASE_URL}/admin/crawl/suggested-since-date")
            resp.raise_for_status()
            data = resp.json()
            return data.get("since_date")
    except Exception:
        return None


def admin_crawl_trigger(
    max_jobs_per_group: int | None = 3,
    max_pages: int = 1,
    max_posts_per_page: int = 10,
    since_date: str | None = None,
    background: bool = True,
) -> dict:
    """수동 크롤링 실행. since_date가 있으면 해당 날짜 이후 작성글만 수집.
    background=True면 백그라운드 실행 후 202 반환(진행률·로그 폴링 가능).
    """
    payload = {
        "max_jobs_per_group": max_jobs_per_group,
        "max_pages": max_pages,
        "max_posts_per_page": max_posts_per_page,
        "background": background,
    }
    if since_date:
        payload["since_date"] = since_date
    with httpx.Client(timeout=30.0 if background else 300.0) as client:
        resp = client.post(f"{API_BASE_URL}/admin/crawl", json=payload)
        # 202 Accepted = 백그라운드 시작됨
        if resp.status_code == 202:
            return resp.json()
        resp.raise_for_status()
        return resp.json()


def admin_crawl_history() -> list[dict]:
    """최근 크롤링 이력."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{API_BASE_URL}/admin/crawl/history")
            resp.raise_for_status()
            data = resp.json()
            return data.get("history", [])
    except Exception:
        return []


def admin_health() -> dict:
    """Admin 헬스 체크."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{API_BASE_URL}/admin/health")
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        return {"status": "error", "qdrant_status": str(e), "document_count": 0}


def admin_qdrant_stats() -> dict:
    """Qdrant 현황 (직업/직업군별 개수)."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_BASE_URL}/admin/qdrant/stats")
        resp.raise_for_status()
        return resp.json()


def admin_qdrant_documents(
    job: str | None = None,
    job_group: str | None = None,
    limit: int = 20,
    offset: str | None = None,
) -> dict:
    """Qdrant 저장 문서 목록 (필터·페이징)."""
    params: dict = {"limit": limit}
    if job:
        params["job"] = job
    if job_group:
        params["직업군"] = job_group
    if offset is not None:
        params["offset"] = offset
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{API_BASE_URL}/admin/qdrant/documents", params=params)
        resp.raise_for_status()
        return resp.json()
