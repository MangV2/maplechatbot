"""구글 소셜 로그인 API."""
import secrets
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import httpx

from app.auth.jwt import create_access_token
from app.config import settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

# 로그인 시 사용할 state 저장 (실제로는 Redis 등 사용 권장)
_auth_states: dict[str, bool] = {}


@router.get("/google")
def auth_google():
    """구글 로그인 페이지로 리다이렉트."""
    if not settings.google_client_id:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth가 설정되지 않았습니다. GOOGLE_CLIENT_ID를 설정하세요.",
        )
    state = secrets.token_urlsafe(32)
    _auth_states[state] = True
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _callback_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{settings.google_auth_url}?{urlencode(params)}"
    return RedirectResponse(url=url)


def _callback_uri() -> str:
    """OAuth 콜백 URL (Google Cloud Console에 등록한 값과 동일해야 함)."""
    base = settings.auth_redirect_base.rstrip("/")
    return f"{base}/auth/google/callback"


@router.get("/google/callback")
def auth_google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """구글 OAuth 콜백. 코드 교환 후 사용자 생성/조회, JWT 발급, 프론트로 리다이렉트."""
    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error={error}",
            status_code=302,
        )
    if not code or not state:
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=missing_params",
            status_code=302,
        )
    if state not in _auth_states:
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=invalid_state",
            status_code=302,
        )
    del _auth_states[state]

    # 코드 → 액세스 토큰
    with httpx.Client() as client:
        token_resp = client.post(
            settings.google_token_url,
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": _callback_uri(),
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.error("Google token error: %s", token_resp.text)
            return RedirectResponse(
                url=f"{settings.frontend_url}?auth_error=token_exchange_failed",
                status_code=302,
            )
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return RedirectResponse(
                url=f"{settings.frontend_url}?auth_error=no_access_token",
                status_code=302,
            )

        # 사용자 정보 조회
        userinfo_resp = client.get(
            settings.google_userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.error("Google userinfo error: %s", userinfo_resp.text)
            return RedirectResponse(
                url=f"{settings.frontend_url}?auth_error=userinfo_failed",
                status_code=302,
            )
        userinfo = userinfo_resp.json()

    email = userinfo.get("email")
    provider_id = userinfo.get("id", "")
    if not email:
        return RedirectResponse(
            url=f"{settings.frontend_url}?auth_error=no_email",
            status_code=302,
        )

    # 사용자 생성 또는 조회
    user = db.query(User).filter(
        User.provider == "google",
        User.provider_id == provider_id,
    ).first()
    if not user:
        user = User(
            email=email,
            provider="google",
            provider_id=provider_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token(str(user.id), user.email)
    redirect_url = f"{settings.frontend_url}?token={token}"
    return RedirectResponse(url=redirect_url, status_code=302)
