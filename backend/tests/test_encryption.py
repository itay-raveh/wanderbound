"""Unit tests for Fernet encryption helpers."""

from app.core.encryption import (
    decrypt_token,
    encrypt_token,
    try_decrypt_token,
)


class TestTokenEncryption:
    def test_round_trip_preserves_value(self) -> None:
        original = "1//0abcdef-ghijklm_nopqrst"
        encrypted = encrypt_token(original)
        assert encrypted != original
        assert decrypt_token(encrypted) == original

    def test_try_decrypt_returns_none_on_invalid(self) -> None:
        assert try_decrypt_token("not-valid-fernet-data") is None

    def test_try_decrypt_returns_plaintext_on_valid(self) -> None:
        encrypted = encrypt_token("secret")
        assert try_decrypt_token(encrypted) == "secret"
