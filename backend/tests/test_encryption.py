"""Unit tests for Fernet encryption helpers."""

import pytest
from cryptography.fernet import InvalidToken

from app.core.encryption import decrypt_token, encrypt_token


class TestTokenEncryption:
    def test_round_trip_preserves_value(self) -> None:
        original = "1//0abcdef-ghijklm_nopqrst"
        encrypted = encrypt_token(original)
        assert encrypted != original
        assert decrypt_token(encrypted) == original

    def test_different_inputs_produce_different_ciphertext(self) -> None:
        a = encrypt_token("token-a")
        b = encrypt_token("token-b")
        assert a != b

    def test_decrypt_invalid_ciphertext_raises(self) -> None:
        with pytest.raises(InvalidToken):
            decrypt_token("not-valid-fernet-data")

    def test_empty_string_round_trips(self) -> None:
        encrypted = encrypt_token("")
        assert decrypt_token(encrypted) == ""
