"""Fernet symmetric encryption for sensitive tokens (e.g. OAuth refresh tokens).

Derives a stable Fernet key from SECRET_KEY so encrypted values survive restarts.
"""

import base64
import hashlib
from functools import cache

from cryptography.fernet import Fernet

from app.core.config import get_settings


@cache
def _fernet() -> Fernet:
    """Derive a stable Fernet key from SECRET_KEY (cached for process lifetime)."""
    digest = hashlib.sha256(get_settings().SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
