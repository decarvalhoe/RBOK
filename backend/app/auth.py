from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

SECRET_KEY = os.getenv("REALISONS_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class Token(BaseModel):
    """Bearer token returned after a successful authentication."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data extracted from the access token payload."""

    username: str
    role: str
    exp: Optional[int] = None


class User(BaseModel):
    """Public user model exposed through dependencies."""

    username: str
    full_name: Optional[str] = None
    disabled: bool = False
    role: str = "user"


class UserInDB(User):
    """Internal user model storing hashed credentials."""

    hashed_password: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check whether the provided password matches the stored hash."""

    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using a strong algorithm suitable for storage."""

    return pwd_context.hash(password)


def _seed_users() -> Dict[str, UserInDB]:
    """Create a deterministic in-memory user store for development and tests."""

    seed_data = {
        "alice": {
            "full_name": "Alice Admin",
            "password": "adminpass",
            "role": "admin",
        },
        "audra": {
            "full_name": "Audra Auditor",
            "password": "auditpass",
            "role": "auditor",
        },
        "bob": {
            "full_name": "Bob Builder",
            "password": "userpass",
            "role": "user",
        },
    }
    users: Dict[str, UserInDB] = {}
    for username, info in seed_data.items():
        users[username] = UserInDB(
            username=username,
            full_name=info["full_name"],
            role=info["role"],
            hashed_password=get_password_hash(info["password"]),
        )
    return users


# In-memory user database seeded for demonstration purposes.
fake_users_db: Dict[str, UserInDB] = _seed_users()

# Role hierarchy used to compare permissions. Higher value == more privileges.
ROLE_LEVELS = {"user": 0, "auditor": 5, "admin": 10}


def get_user(username: str) -> Optional[UserInDB]:
    """Retrieve a user from the in-memory store."""

    return fake_users_db.get(username)


def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    """Validate a user's credentials."""

    user = get_user(username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: Dict[str, str], expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token."""

    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """FastAPI dependency that resolves the currently authenticated user."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        role: Optional[str] = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
    except JWTError as exc:  # pragma: no cover - defensive branch
        raise credentials_exception from exc

    user = get_user(username)
    if user is None:
        raise credentials_exception
    if user.disabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")

    return user


def require_role(required_role: str):
    """Factory returning a dependency that enforces a minimum role."""

    required_level = ROLE_LEVELS.get(required_role, float("inf"))

    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        current_level = ROLE_LEVELS.get(current_user.role, -1)
        if current_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_dependency


def get_current_user_optional(token: Optional[str] = Depends(optional_oauth2_scheme)) -> Optional[User]:
    """Resolve the current user when authentication is optional."""

    if not token:
        return None
    return get_current_user(token=token)

__all__ = [
    "Token",
    "TokenData",
    "User",
    "authenticate_user",
    "create_access_token",
    "get_current_user",
    "require_role",
]
