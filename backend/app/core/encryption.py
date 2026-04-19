"""Fernet symmetric encryption for sensitive tokens (e.g. OAuth refresh tokens).

Derives a stable Fernet key from SECRET_KEY via HKDF so encrypted values
survive restarts. Supports zero-downtime key rotation via MultiFernet
when SECRET_KEY_PREVIOUS is set.
"""

import base64
import logging
from functools import cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Salt and info are not secret: https://datatracker.ietf.org/doc/html/rfc5869#section-3.1
_SALT = b"wanderbound-hkdf-v1"
_INFO = b"wanderbound-token-encryption"


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a url-safe Fernet key from an arbitrary secret via HKDF."""
    raw = HKDF(algorithm=SHA256(), length=32, salt=_SALT, info=_INFO).derive(
        secret.encode()
    )
    return base64.urlsafe_b64encode(raw)


@cache
def _fernet() -> Fernet | MultiFernet:
    """Build a Fernet (or MultiFernet for key rotation) from settings."""
    settings = get_settings()
    current = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    if settings.SECRET_KEY_PREVIOUS:
        previous = Fernet(_derive_fernet_key(settings.SECRET_KEY_PREVIOUS))
        return MultiFernet([current, previous])
    return current


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def try_decrypt_token(ciphertext: str) -> str | None:
    """Decrypt, returning None if the token is unreadable (e.g. key rotation)."""
    try:
        return decrypt_token(ciphertext)
    except InvalidToken:
        logger.warning("Failed to decrypt token - SECRET_KEY may have rotated")
        return None
