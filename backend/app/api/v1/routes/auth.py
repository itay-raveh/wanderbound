import asyncio
import logging

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from jwt import PyJWKClient
from pydantic import BaseModel
from sqlmodel import select

from app.core.config import get_settings
from app.models.user import GoogleIdentity, User

from ..deps import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_jwks_client = PyJWKClient(
    "https://www.googleapis.com/oauth2/v3/certs", cache_keys=True, lifespan=3600
)

GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleCredential(BaseModel):
    credential: str


async def verify_google_credential(credential: str) -> GoogleIdentity:
    """Verify a Google ID token JWT and return the validated identity."""
    try:
        signing_key = await asyncio.to_thread(
            _jwks_client.get_signing_key_from_jwt, credential
        )
        payload = jwt.decode(
            credential,
            signing_key.key,
            algorithms=["RS256"],
            audience=get_settings().VITE_GOOGLE_CLIENT_ID,
            issuer=GOOGLE_ISSUERS,
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED) from None

    return GoogleIdentity(
        sub=payload["sub"],
        first_name=payload.get("given_name", ""),
        last_name=payload.get("family_name", ""),
        picture=payload.get("picture"),
    )


@router.post("/google")
async def auth_google(
    body: GoogleCredential, request: Request, session: SessionDep
) -> User | None:
    identity = await verify_google_credential(body.credential)

    row = (
        await session.exec(select(User).where(User.google_sub == identity.sub))
    ).first()

    if row is None:
        logger.info("New Google identity: sub=%s", identity.sub)
        return None

    request.session.clear()
    request.session["uid"] = row.id
    logger.info("Existing user %d signed in", row.id)
    return row


@router.post("/logout")
async def logout(request: Request) -> None:
    request.session.clear()
