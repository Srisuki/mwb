import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_passwords_are_hashed_and_verified():
    password = "A-strong-production-password-2026"
    password_hash = hash_password(password)
    assert password not in password_hash
    assert verify_password(password, password_hash)
    assert not verify_password("incorrect", password_hash)


def test_access_token_round_trip():
    assert decode_access_token(create_access_token("user-123")) == "user-123"


def test_rejects_invalid_token():
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token("not-a-token")
