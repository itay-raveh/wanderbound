import asyncio
import re
from typing import Literal

import jwt
import structlog
from fastapi import APIRouter, HTTPException, Request, status
from jwt import PyJWKClient
from pydantic import BaseModel
from sqlmodel import select

from app.core.config import get_settings
from app.models.user import AuthProvider, OAuthIdentity, User, UserPublic

from ..deps import SessionDep, login_session, to_user_public, try_load_user

PENDING_SIGNUP_KEY = "pending_signup"

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_google_jwks = PyJWKClient(
    "https://www.googleapis.com/oauth2/v3/certs", cache_keys=True, lifespan=3600
)
_microsoft_jwks = PyJWKClient(
    "https://login.microsoftonline.com/common/discovery/v2.0/keys",
    cache_keys=True,
    lifespan=3600,
)

GOOGLE_ISSUERS = ["accounts.google.com", "https://accounts.google.com"]
_MS_ISSUER_RE = re.compile(r"^https://login\.microsoftonline\.com/[0-9a-f-]{36}/v2\.0$")


class Credential(BaseModel):
    credential: str


async def _verify_oidc_token(
    credential: str,
    jwks_client: PyJWKClient,
    audience: str,
    issuer: list[str] | None,
) -> dict:
    def _decode() -> dict:
        key = jwks_client.get_signing_key_from_jwt(credential)
        return jwt.decode(
            credential,
            key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"verify_iss": issuer is not None},
        )

    try:
        return await asyncio.to_thread(_decode)
    except jwt.InvalidTokenError as e:
        logger.warning("auth.oidc_verification_failed", error_type=type(e).__name__)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED) from None


async def _verify_google(credential: str) -> OAuthIdentity:
    settings = get_settings()
    if not settings.VITE_GOOGLE_CLIENT_ID:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, "Google auth not configured"
        )
    payload = await _verify_oidc_token(
        credential, _google_jwks, settings.VITE_GOOGLE_CLIENT_ID, GOOGLE_ISSUERS
    )
    return OAuthIdentity(
        sub=payload["sub"],
        first_name=payload.get("given_name", ""),
        picture=payload.get("picture"),
        provider="google",
    )


async def _verify_microsoft(credential: str) -> OAuthIdentity:
    settings = get_settings()
    if not settings.VITE_MICROSOFT_CLIENT_ID:
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, "Microsoft auth not configured"
        )
    payload = await _verify_oidc_token(
        credential, _microsoft_jwks, settings.VITE_MICROSOFT_CLIENT_ID, issuer=None
    )
    # /common issues tenant-specific issuers - pattern-match manually.
    iss = payload.get("iss", "")
    if not _MS_ISSUER_RE.match(iss):
        logger.warning("auth.microsoft_unexpected_issuer")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return OAuthIdentity(
        sub=payload["sub"],
        first_name=payload.get("given_name") or payload.get("name", ""),
        provider="microsoft",
    )


_VERIFIERS = {"google": _verify_google, "microsoft": _verify_microsoft}


async def verify_credential(credential: str, provider: AuthProvider) -> OAuthIdentity:
    return await _VERIFIERS[provider](credential)


_PROVIDER_COL = {"google": User.google_sub, "microsoft": User.microsoft_sub}


async def _lookup_user(identity: OAuthIdentity, session: SessionDep) -> User | None:
    col = _PROVIDER_COL[identity.provider]
    return (await session.exec(select(User).where(col == identity.sub))).first()


def set_pending_signup(request: Request, identity: OAuthIdentity) -> None:
    request.session[PENDING_SIGNUP_KEY] = {
        "provider": identity.provider,
        "sub": identity.sub,
        "first_name": identity.first_name,
        "picture": str(identity.picture) if identity.picture else None,
    }


def clear_pending_signup(request: Request) -> None:
    request.session.pop(PENDING_SIGNUP_KEY, None)


def get_pending_signup(request: Request) -> OAuthIdentity | None:
    blob = request.session.get(PENDING_SIGNUP_KEY)
    if not blob:
        return None
    return OAuthIdentity(
        sub=blob["sub"],
        first_name=blob.get("first_name", ""),
        picture=blob.get("picture"),
        provider=blob["provider"],
    )


async def _authenticate(
    credential: str, provider: AuthProvider, request: Request, session: SessionDep
) -> User | None:
    identity = await verify_credential(credential, provider)
    row = await _lookup_user(identity, session)
    if row is None:
        logger.info("auth.identity_created", provider=provider)
        set_pending_signup(request, identity)
        return None
    login_session(request, row.id)
    logger.info("auth.sign_in", user_id=row.id, provider=provider)
    return row


@router.post("/logout")
async def logout(request: Request) -> None:
    request.session.clear()


class AuthState(BaseModel):
    state: Literal["authenticated", "pending_signup", "anonymous"]
    user: UserPublic | None = None
    pending_first_name: str | None = None
    pending_picture: str | None = None


@router.get("/state")
async def auth_state(request: Request, session: SessionDep) -> AuthState:
    if user := await try_load_user(request, session):
        return AuthState(
            state="authenticated", user=await to_user_public(user, session)
        )
    if pending := get_pending_signup(request):
        return AuthState(
            state="pending_signup",
            pending_first_name=pending.first_name,
            pending_picture=str(pending.picture) if pending.picture else None,
        )
    return AuthState(state="anonymous")


@router.post("/{provider}")
async def authenticate(
    provider: AuthProvider, body: Credential, request: Request, session: SessionDep
) -> UserPublic | None:
    user = await _authenticate(body.credential, provider, request, session)
    return await to_user_public(user, session) if user else None
