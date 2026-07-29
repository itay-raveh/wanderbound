import base64
import hashlib
import secrets
from typing import TYPE_CHECKING

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

if TYPE_CHECKING:
    from fastapi import Response

_OAUTH_COOKIE = "gphotos_oauth"
_OAUTH_COOKIE_PATH = "/api/v1/google-photos/callback"
_STATE_TTL_S = 600


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().SECRET_KEY, salt="gphotos-oauth-state")


def _oauth_cookie_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        get_settings().SECRET_KEY, salt="gphotos-oauth-cookie"
    )


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def issue_oauth_cookie(response: Response) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    signed = _oauth_cookie_serializer().dumps({"csrf": csrf, "verifier": verifier})
    response.set_cookie(
        _OAUTH_COOKIE,
        signed,
        max_age=_STATE_TTL_S,
        httponly=True,
        secure=get_settings().ENVIRONMENT != "local",
        samesite="lax",
        path=_OAUTH_COOKIE_PATH,
    )
    return csrf, verifier


def decode_oauth_cookie(raw: str | None) -> dict[str, str] | None:
    if raw is None:
        return None
    try:
        return _oauth_cookie_serializer().loads(raw, max_age=_STATE_TTL_S)
    except BadSignature, SignatureExpired:
        return None


def clear_oauth_cookie(response: Response) -> None:
    response.delete_cookie(_OAUTH_COOKIE, path=_OAUTH_COOKIE_PATH)


def encode_state(csrf: str, nonce: str, redirect_uri: str) -> str:
    return _state_serializer().dumps(
        {"csrf": csrf, "nonce": nonce, "redirect_uri": redirect_uri}
    )


def decode_state(token: str) -> dict[str, str] | None:
    try:
        return _state_serializer().loads(token, max_age=_STATE_TTL_S)
    except BadSignature, SignatureExpired:
        return None
