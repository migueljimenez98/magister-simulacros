"""JWT + password hashing helpers. Single tenant, no fancy claims."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from .config import settings


# Using bcrypt directly instead of passlib — passlib's CryptContext breaks
# on bcrypt 4.x because of an internal backend detection bug (it raises the
# "password > 72 bytes" error even for 8-char passwords). bcrypt's own API
# is stable and trivial.


def _encode(plain: str) -> bytes:
    b = plain.encode("utf-8")
    # bcrypt silently truncates above 72 bytes in its native C code on most
    # platforms, but our bindings raise instead — truncate here so long
    # passphrases don't block login. Equivalent to crypt.h behaviour.
    return b[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(*, subject: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={
                "require": ["exp", "sub"],
                "verify_exp": True,
            },
        )
    except InvalidTokenError as e:
        raise ValueError(str(e)) from e
