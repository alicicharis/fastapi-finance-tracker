import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User

class AuthError(Exception):
    pass


class InvalidCredentials(AuthError):
    pass


class DuplicateEmail(AuthError):
    pass


class InvalidToken(AuthError):
    pass


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_TTL_MIN),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise InvalidToken("invalid or expired access token")


def _hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def issue_refresh_token(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, RefreshToken]:
    plain = secrets.token_urlsafe(32)
    row = RefreshToken(
        user_id=user_id,
        token_hash=_hash_refresh(plain),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS),
    )
    db.add(row)
    await db.flush()
    return plain, row


async def rotate_refresh_token(db: AsyncSession, plain_token: str) -> tuple[User, str, str]:
    token_hash = _hash_refresh(plain_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    row = result.scalar_one_or_none()

    if row is None:
        raise InvalidToken("refresh token not found")
    if row.revoked_at is not None:
        raise InvalidToken("refresh token has been revoked")
    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise InvalidToken("refresh token has expired")

    row.revoked_at = datetime.now(timezone.utc)
    db.add(row)

    user_result = await db.execute(select(User).where(User.id == row.user_id))
    user = user_result.scalar_one()

    access = create_access_token(user.id)
    new_plain, _ = await issue_refresh_token(db, user.id)
    return user, access, new_plain


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none() is not None:
        raise DuplicateEmail(f"email already registered: {email}")

    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user
