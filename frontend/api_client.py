"""백엔드 API 통신 클라이언트."""
import json
import os
from typing import Generator

import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
# 브라우저가 직접 이동하는 URL (로그인 링크 등). Docker에서는 localhost:8000 필요
API_PUBLIC_URL = os.getenv("API_PUBLIC_URL", API_BASE_URL)
REQUEST_TIMEOUT = 30.0


def _headers(token: str | None = None) -> dict:
    """Authorization 헤더 (토큰이 있으면 Bearer 추가)."""
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ── 채팅 API ───────────────────────────────────────────


def chat(
    query: str,
    top_k: int = 5,
    use_cot: bool = True,
    token: str | None = None,
) -> dict:
    """동기 채팅 API 호출. token이 있으면 본캐 정보가 에이전트에 전달됨."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.post(
            f"{API_BASE_URL}/chat",
            json={"query": query, "top_k": top_k, "use_cot": use_cot},
            headers=_headers(token),
        )
        response.raise_for_status()
        return response.json()


def chat_stream(
    query: str,
    top_k: int = 5,
    use_cot: bool = True,
    token: str | None = None,
) -> Generator[dict, None, None]:
    """SSE 스트리밍 채팅 API 호출. token이 있으면 본캐 정보가 에이전트에 전달됨."""
    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        with client.stream(
            "POST",
            f"{API_BASE_URL}/chat/stream",
            json={"query": query, "top_k": top_k, "use_cot": use_cot},
            headers=_headers(token),
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


def list_sessions(
    limit: int = 100, offset: int = 0, token: str | None = None
) -> list[dict]:
    """세션 목록 조회 (페이징). token 있으면 본인 세션만, 없으면 익명 세션만."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{API_BASE_URL}/sessions",
                params={"limit": limit, "offset": offset},
                headers=_headers(token),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return []


def create_session(token: str | None = None) -> dict:
    """새 세션 생성. token 있으면 user_id 연결."""
    with httpx.Client(timeout=5.0) as client:
        resp = client.post(
            f"{API_BASE_URL}/sessions",
            headers=_headers(token),
        )
        resp.raise_for_status()
        return resp.json()


def get_session(session_id: str, token: str | None = None) -> dict | None:
    """세션 상세 (메시지 포함) 조회."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{API_BASE_URL}/sessions/{session_id}",
                headers=_headers(token),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def save_message(
    session_id: str,
    role: str,
    content: str,
    references: list | None = None,
    token: str | None = None,
):
    """세션에 메시지 저장."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(
                f"{API_BASE_URL}/sessions/{session_id}/messages",
                json={"role": role, "content": content, "references": references},
                headers=_headers(token),
            )
            resp.raise_for_status()
    except Exception:
        pass  # 저장 실패해도 UI는 계속 동작


def delete_session(session_id: str, token: str | None = None):
    """세션 삭제."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.delete(
                f"{API_BASE_URL}/sessions/{session_id}",
                headers=_headers(token),
            )
            resp.raise_for_status()
    except Exception:
        pass


# ── 인증 API ──────────────────────────────────────────


def auth_google_login_url() -> str:
    """구글 로그인 URL (브라우저가 이동 → API_PUBLIC_URL 사용)."""
    return f"{API_PUBLIC_URL}/auth/google"


def get_me(token: str) -> dict | None:
    """현재 로그인 사용자 조회."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"{API_BASE_URL}/users/me",
                headers=_headers(token),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def update_main_character(token: str, main_character_name: str) -> dict | None:
    """본캐 닉네임 등록/수정."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.patch(
                f"{API_BASE_URL}/users/me/main-character",
                json={"main_character_name": main_character_name},
                headers=_headers(token),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


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


def admin_user_count() -> int:
    """관리자용: 가입 회원 수."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{API_BASE_URL}/admin/users/count")
            resp.raise_for_status()
            return resp.json().get("count", 0)
    except Exception:
        return 0


def admin_list_users() -> list[dict]:
    """관리자용: 회원 목록 (id, email, 본캐)."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{API_BASE_URL}/admin/users")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return []


def admin_list_sessions(
    limit: int = 100, offset: int = 0, user_id: str | None = None
) -> list[dict]:
    """관리자용: 세션 목록. user_id로 필터 가능 (__anonymous__=익명만)."""
    try:
        params: dict = {"limit": limit, "offset": offset}
        if user_id is not None:
            params["user_id"] = user_id
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{API_BASE_URL}/admin/sessions", params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return []


def admin_get_session(session_id: str) -> dict | None:
    """관리자용: 세션 상세 (메시지 포함) 조회."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{API_BASE_URL}/admin/sessions/{session_id}")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def admin_delete_session(session_id: str):
    """관리자용: 세션 삭제."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.delete(f"{API_BASE_URL}/admin/sessions/{session_id}")
            resp.raise_for_status()
    except Exception:
        pass


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
    since_date: str | None = None,
    crawl_mode: str = "all",
    background: bool = True,
) -> dict:
    """수동 크롤링 실행. since_date가 있으면 해당 날짜 이후 작성글만 수집.
    crawl_mode: job_only(직업게시판만), flat_only(단일게시판만), all(전체)
    background=True면 백그라운드 실행 후 202 반환(진행률·로그 폴링 가능).
    """
    payload = {
        "crawl_mode": crawl_mode,
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
