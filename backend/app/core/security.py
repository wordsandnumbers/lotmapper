import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_fingerprint(password_hash: str) -> str:
    """Short stable fingerprint of a bcrypt hash, used to invalidate reset
    tokens once the password changes. SHA-256 truncated to 16 hex chars.
    """
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:16]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.access_token_expire_minutes
        )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.secret_key, algorithm=settings.algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        return payload
    except JWTError:
        return None


def create_signup_token(user_id: UUID, expires_hours: int = 72) -> str:
    expire = datetime.utcnow() + timedelta(hours=expires_hours)
    payload = {"sub": str(user_id), "type": "signup", "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_signup_token(token: str) -> Optional[UUID]:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError:
        return None
    if payload.get("type") != "signup":
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        return UUID(sub)
    except (ValueError, TypeError):
        return None


def create_reset_token(
    user_id: UUID, password_hash: str, expires_hours: int = 1
) -> str:
    """Reset token bound to the current password hash — one-shot per password.

    After the password is changed (or reset succeeds), the fingerprint stops
    matching and any outstanding token becomes invalid.
    """
    expire = datetime.utcnow() + timedelta(hours=expires_hours)
    payload = {
        "sub": str(user_id),
        "type": "reset",
        "fp": _hash_fingerprint(password_hash),
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_reset_token(token: str) -> Optional[Tuple[UUID, str]]:
    """Return (user_id, fingerprint) if the token is well-formed and unexpired.

    The caller must compare the fingerprint against the user's current
    `password_hash` to confirm the token hasn't been consumed.
    """
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
    except JWTError:
        return None
    if payload.get("type") != "reset":
        return None
    sub = payload.get("sub")
    fp = payload.get("fp")
    if not sub or not fp:
        return None
    try:
        return UUID(sub), fp
    except (ValueError, TypeError):
        return None
