import asyncio
import logging
import re

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from jwt import PyJWKClient
from pydantic import BaseModel
from sqlmodel import select

from app.core.config import get_settings
from app.models.user import OAuthIdentity, Provider, User

from ..deps import SessionDep

logger = logging.getLogger(__name__)

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
        logger.warning("OIDC JWT verification failed: %s", e)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED) from None


async def _verify_google(credential: str) -> OAuthIdentity:
    settings = get_settings()
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
    # /common issues tenant-specific issuers — pattern-match manually.
    iss = payload.get("iss", "")
    if not _MS_ISSUER_RE.match(iss):
        logger.warning("Microsoft token has unexpected issuer: %s", iss)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return OAuthIdentity(
        sub=payload["sub"],
        first_name=payload.get("given_name") or payload.get("name", ""),
        provider="microsoft",
    )


_VERIFIERS = {"google": _verify_google, "microsoft": _verify_microsoft}


async def verify_credential(credential: str, provider: Provider) -> OAuthIdentity:
    return await _VERIFIERS[provider](credential)


_PROVIDER_COL = {"google": User.google_sub, "microsoft": User.microsoft_sub}


async def _lookup_user(identity: OAuthIdentity, session: SessionDep) -> User | None:
    col = _PROVIDER_COL[identity.provider]
    return (await session.exec(select(User).where(col == identity.sub))).first()


async def _authenticate(
    credential: str, provider: Provider, request: Request, session: SessionDep
) -> User | None:
    identity = await verify_credential(credential, provider)
    row = await _lookup_user(identity, session)
    if row is None:
        logger.info("New %s identity: sub=%s", provider, identity.sub)
        return None
    request.session.clear()
    request.session["uid"] = row.id
    logger.info("Existing user %d signed in via %s", row.id, provider)
    return row


@router.post("/google")
async def auth_google(
    body: Credential, request: Request, session: SessionDep
) -> User | None:
    return await _authenticate(body.credential, "google", request, session)


@router.post("/microsoft")
async def auth_microsoft(
    body: Credential, request: Request, session: SessionDep
) -> User | None:
    return await _authenticate(body.credential, "microsoft", request, session)


@router.post("/logout")
async def logout(request: Request) -> None:
    request.session.clear()
