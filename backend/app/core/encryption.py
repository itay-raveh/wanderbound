"""Fernet symmetric encryption for sensitive tokens (e.g. OAuth refresh tokens).

Derives a stable Fernet key from SECRET_KEY so encrypted values survive restarts.
"""

import base64
import hashlib
import logging
from functools import cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@cache
def _fernet() -> Fernet:
    """Derive a stable Fernet key from SECRET_KEY (cached for process lifetime)."""
    digest = hashlib.sha256(get_settings().SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


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
