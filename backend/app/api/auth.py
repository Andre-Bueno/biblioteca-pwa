"""Auth routes (`/api/v1/auth`). Thin: validate, call `AuthService`, set cookies, map errors.

Cookies (all host-only: no `Domain`; `SameSite=Strict`; `Secure` follows COOKIE_SECURE):
  access_token   HttpOnly  Path=/api              short-lived JWT
  refresh_token  HttpOnly  Path=/api/v1/auth      opaque, rotated on every use
  csrf_token     JS-readable (by design: double submit)  Path=/   signed, see `api/csrf.py`

Why no `__Host-` prefix: the prefix forces `Path=/`, which would defeat the narrower paths of the
session cookies (the refresh token must not travel to every /api route); the CSRF cookie name is
fixed by the frontend contract (`csrf_token`); and `__Host-` requires `Secure`, which local HTTP
development (COOKIE_SECURE=false) cannot provide. Host-only + Strict + Path scoping + the signed
CSRF token cover the same threats (cookie tossing from sibling subdomains cannot forge a
CSRF token).

Login/refresh never return tokens in the body.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.auth_schemas import ChangePasswordRequest, LoginRequest, UserOut
from app.api.csrf import CSRF_COOKIE_NAME, CsrfTokenSigner
from app.api.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    get_auth_service,
    get_csrf_signer,
    get_current_user,
    get_settings_dep,
)
from app.api.errors import BUSY_DETAIL
from app.api.http_utils import client_ip, is_non_public_address, raw_client_host
from app.core.config import Settings
from app.domain.auth import (
    CurrentPasswordError,
    InvalidCredentialsError,
    InvalidSessionError,
    LoginLockedError,
)
from app.domain.errors import ResourceBusy
from app.domain.password_policy import PasswordPolicyError
from app.domain.user import User
from app.services.auth_service import AuthService, IssuedSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

AUTH_COOKIE_PATH = "/api/v1/auth"
LOCKED_DETAIL = "Too many requests. Try again later."  # same text as the rate limiter

AuthDep = Annotated[AuthService, Depends(get_auth_service)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
CurrentUser = Annotated[User, Depends(get_current_user)]


_private_client_warned = False


def _ip(request: Request) -> str:
    """Client key for the login limits (`http_utils.client_ip`) plus a one-shot proxy warning."""
    global _private_client_warned  # one-shot log flag; a benign race at worst logs twice
    if not _private_client_warned and is_non_public_address(raw_client_host(request.scope)):
        _private_client_warned = True
        # Generic on purpose: no address is logged.
        logger.warning(
            "A login request came from a private/loopback address. If the app is behind a "
            "reverse proxy, FORWARDED_ALLOW_IPS must name the proxy, otherwise every client "
            "shares one address and the per-address login limits apply to all of them."
        )
    return client_ip(request.scope)


def _busy() -> HTTPException:
    return HTTPException(status_code=503, detail=BUSY_DETAIL, headers={"Retry-After": "1"})


def _locked(exc: LoginLockedError) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail=LOCKED_DETAIL,
        headers={"Retry-After": str(exc.retry_after_seconds)},
    )


def _set_session_cookies(response: Response, settings: Settings, session: IssuedSession) -> None:
    common = {"httponly": True, "secure": settings.COOKIE_SECURE, "samesite": "strict"}
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=session.access_max_age_seconds,
        path="/api",
        **common,  # type: ignore[arg-type]
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=session.refresh_max_age_seconds,
        path=AUTH_COOKIE_PATH,
        **common,  # type: ignore[arg-type]
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    for name, path in ((ACCESS_COOKIE, "/api"), (REFRESH_COOKIE, AUTH_COOKIE_PATH)):
        response.delete_cookie(
            name,
            path=path,
            secure=settings.COOKIE_SECURE,
            httponly=True,
            samesite="strict",
        )


def _set_csrf_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS,
        path="/",
        secure=settings.COOKIE_SECURE,
        httponly=False,  # the frontend must read it to echo it in X-CSRF-Token
        samesite="strict",
    )


@router.get("/csrf", status_code=204)
def csrf(
    request: Request,
    settings: SettingsDep,
    signer: Annotated[CsrfTokenSigner, Depends(get_csrf_signer)],
) -> Response:
    """Issue the CSRF cookie (reuses the current one while it is still valid)."""
    token = request.cookies.get(CSRF_COOKIE_NAME)
    response = Response(status_code=204)
    _set_csrf_cookie(
        response, settings, token if signer.is_valid(token) and token else signer.issue()
    )
    return response


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest, request: Request, response: Response, auth: AuthDep, settings: SettingsDep
) -> UserOut:
    try:
        session = auth.login(body.username, body.password, _ip(request))
    except LoginLockedError as exc:
        raise _locked(exc) from None
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None
    except ResourceBusy:
        raise _busy() from None  # same answer for known and unknown accounts
    _set_session_cookies(response, settings, session)
    return UserOut.from_domain(session.user)


@router.post("/refresh", status_code=204)
def refresh(request: Request, auth: AuthDep, settings: SettingsDep) -> Response:
    try:
        session = auth.refresh(request.cookies.get(REFRESH_COOKIE))
    except InvalidSessionError:
        response = Response(
            content='{"detail":"Not authenticated"}',
            status_code=401,
            media_type="application/json",
        )
        _clear_session_cookies(response, settings)  # a dead session must not linger
        return response
    response = Response(status_code=204)
    _set_session_cookies(response, settings, session)
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, auth: AuthDep, settings: SettingsDep) -> Response:
    auth.logout(request.cookies.get(REFRESH_COOKIE), request.cookies.get(ACCESS_COOKIE))
    response = Response(status_code=204)
    _clear_session_cookies(response, settings)
    return response


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_domain(user)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: CurrentUser,
    auth: AuthDep,
    settings: SettingsDep,
) -> Response:
    try:
        session = auth.change_password(
            user.id, body.current_password, body.new_password, _ip(request)
        )
    except LoginLockedError as exc:
        raise _locked(exc) from None
    except ResourceBusy:
        raise _busy() from None
    except CurrentPasswordError:
        raise HTTPException(status_code=403, detail="Current password is incorrect") from None
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    response = Response(status_code=204)
    _set_session_cookies(response, settings, session)
    return response
