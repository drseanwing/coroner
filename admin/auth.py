"""
Patient Safety Monitor - Authentication Service

OAuth2 JWT token-based authentication for the admin dashboard.
Provides token creation, validation, and password hashing utilities.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel

from config.settings import get_settings


# =============================================================================
# Password Hashing Context
# =============================================================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =============================================================================
# Token Models
# =============================================================================

class Token(BaseModel):
    """OAuth2 token response model."""
    access_token: str
    token_type: str
    expires_at: datetime


class TokenData(BaseModel):
    """Decoded token payload data."""
    username: Optional[str] = None
    role: str = "user"


class User(BaseModel):
    """User model for role-based access control."""
    username: str
    role: str = "admin"
    disabled: bool = False


# =============================================================================
# Password Utilities
# =============================================================================

def get_password_hash(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Bcrypt hash string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to verify against

    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


# =============================================================================
# JWT Token Functions
# =============================================================================

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Payload data to encode in the token
        expires_delta: Optional custom expiration time (defaults to settings)

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token({"sub": "admin", "role": "admin"})
        >>> isinstance(token, str)
        True
    """
    settings = get_settings()

    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_expiration_minutes
        )

    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string to verify

    Returns:
        TokenData with decoded payload

    Raises:
        JWTError: If token is invalid or expired
    """
    settings = get_settings()

    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    username: Optional[str] = payload.get("sub")
    role: str = payload.get("role", "user")

    if username is None:
        raise JWTError("Token missing 'sub' claim")

    return TokenData(username=username, role=role)


def get_token_expiration(
    expires_delta: Optional[timedelta] = None,
) -> datetime:
    """
    Calculate token expiration timestamp.

    Args:
        expires_delta: Optional custom expiration time

    Returns:
        Expiration datetime (UTC)
    """
    settings = get_settings()

    if expires_delta:
        return datetime.now(timezone.utc) + expires_delta
    else:
        return datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_expiration_minutes
        )
