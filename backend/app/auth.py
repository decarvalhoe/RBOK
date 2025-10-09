"""Authentication and authorization utilities relying on Keycloak and OIDC."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Dict, Iterable, Optional, Sequence

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from keycloak import KeycloakOpenID
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class AuthSettings(BaseModel):
    """Runtime configuration for talking to Keycloak and OPA."""

    keycloak_server_url: str = Field(default_factory=lambda: os.getenv("KEYCLOAK_SERVER_URL", "http://localhost:8080"))
    keycloak_realm: str = Field(default_factory=lambda: os.getenv("KEYCLOAK_REALM", "realison"))
    keycloak_client_id: str = Field(default_factory=lambda: os.getenv("KEYCLOAK_CLIENT_ID", "realison-backend"))
    keycloak_client_secret: Optional[str] = Field(default_factory=lambda: os.getenv("KEYCLOAK_CLIENT_SECRET"))
    keycloak_audience: Optional[str] = Field(default_factory=lambda: os.getenv("KEYCLOAK_AUDIENCE"))
    keycloak_role_mapping: Dict[str, str] = Field(default_factory=lambda: _parse_role_mapping(os.getenv("KEYCLOAK_ROLE_MAPPING")))
    opa_url: Optional[str] = Field(default_factory=lambda: os.getenv("OPA_URL"))
    opa_timeout_seconds: float = Field(default_factory=lambda: float(os.getenv("OPA_TIMEOUT_SECONDS", "2.0")))

    model_config = ConfigDict(frozen=True)


def _parse_role_mapping(raw_value: Optional[str]) -> Dict[str, str]:
    """Parse a JSON dictionary mapping Keycloak roles to application roles."""

    default_mapping = {
        "app-admin": "admin",
        "app-user": "user",
    }
    if not raw_value:
        return default_mapping
    try:
        parsed = json.loads(raw_value)
        if not isinstance(parsed, dict):
            raise ValueError("Role mapping must be a JSON object")
        return {str(key): str(value) for key, value in parsed.items()}
    except (ValueError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive branch
        raise RuntimeError("Invalid KEYCLOAK_ROLE_MAPPING value") from exc


@lru_cache()
def get_settings() -> AuthSettings:
    """Return cached authentication settings."""

    return AuthSettings()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
from .env import get_secret_key

SECRET_KEY = get_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
optional_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


class Token(BaseModel):
    """Bearer token returned after a successful authentication or refresh."""

    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    refresh_expires_in: Optional[int] = None


class TokenIntrospection(BaseModel):
    """Introspection response provided by Keycloak."""

    active: bool
    username: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    sub: Optional[str] = None
    scope: Optional[str] = None
    client_id: Optional[str] = None
    aud: Optional[str] = None


class User(BaseModel):
    """Current authenticated user model exposed through dependencies."""

    subject: str
    username: str
    email: Optional[str] = None
    roles: Sequence[str] = Field(default_factory=list)
    role: str = "user"


# ---------------------------------------------------------------------------
# Keycloak helpers
# ---------------------------------------------------------------------------


class KeycloakService:
    """Wrapper around ``python-keycloak`` for token management."""

    def __init__(self, settings: AuthSettings):
        self._settings = settings
        self._openid = KeycloakOpenID(
            server_url=settings.keycloak_server_url,
            realm_name=settings.keycloak_realm,
            client_id=settings.keycloak_client_id,
            client_secret_key=settings.keycloak_client_secret,
        )
        self._cached_public_key: Optional[str] = None

    def _get_public_key(self) -> str:
        """Return the realm public key in PEM format."""

        if self._cached_public_key:
            return self._cached_public_key
        raw_key = self._openid.public_key()
        self._cached_public_key = f"-----BEGIN PUBLIC KEY-----\n{raw_key}\n-----END PUBLIC KEY-----"
        return self._cached_public_key

    def obtain_token(self, username: str, password: str) -> Token:
        """Execute the password grant against Keycloak."""

        token_response = self._openid.token(username=username, password=password)
        return Token(**token_response)

    def refresh_token(self, refresh_token: str) -> Token:
        """Refresh an access token via Keycloak."""

        token_response = self._openid.refresh_token(refresh_token)
        return Token(**token_response)

    def introspect_token(self, token: str) -> TokenIntrospection:
        """Perform token introspection through Keycloak."""

        data = self._openid.introspect(token)
        return TokenIntrospection(**data)

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and verify a bearer token."""

        key = self._get_public_key()
        options = {
            "verify_signature": True,
            "verify_aud": bool(self._settings.keycloak_audience),
            "verify_exp": True,
        }
        try:
            payload: Dict[str, Any] = self._openid.decode_token(
                token,
                key=key,
                options=options,
                audience=self._settings.keycloak_audience,
            )
            return payload
        except Exception as exc:  # pragma: no cover - defensive branch
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    def extract_roles(self, payload: Dict[str, Any]) -> Sequence[str]:
        """Collect all Keycloak roles present in the token payload."""

        roles: set[str] = set()
        realm_roles = payload.get("realm_access", {}).get("roles", [])
        resource_access = payload.get("resource_access", {})
        client_roles = resource_access.get(self._settings.keycloak_client_id, {}).get("roles", [])
        roles.update(realm_roles or [])
        roles.update(client_roles or [])
        return sorted(roles)

    def map_role(self, kc_roles: Iterable[str]) -> str:
        """Map Keycloak roles to the application canonical role."""

        mapping = self._settings.keycloak_role_mapping
        for raw_role in kc_roles:
            if raw_role in mapping:
                return mapping[raw_role]
        # Default to the least privileged role if no mapping matches
        return "user"


@lru_cache()
def get_keycloak_service() -> KeycloakService:
    """Return a cached ``KeycloakService`` instance."""
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

    return KeycloakService(get_settings())


# ---------------------------------------------------------------------------
# OPA client
# ---------------------------------------------------------------------------
# Role hierarchy used to compare permissions. Higher value == more privileges.
ROLE_LEVELS = {"user": 0, "auditor": 5, "admin": 10}


class OPAClient:
    """Simple HTTP client querying an OPA policy endpoint."""

    def __init__(self, url: str, timeout: float) -> None:
        self._url = url.rstrip("/")
        self._timeout = timeout

    def evaluate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = httpx.post(self._url, json=payload, timeout=self._timeout)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="OPA evaluation timed out",
            ) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - defensive branch
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="OPA evaluation failed",
            ) from exc


@lru_cache()
def get_opa_client() -> Optional[OPAClient]:
    settings = get_settings()
    if not settings.opa_url:
        return None
    return OPAClient(settings.opa_url, settings.opa_timeout_seconds)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """FastAPI dependency resolving the currently authenticated user."""

    service = get_keycloak_service()
    try:
        payload = service.decode_token(token)
    except HTTPException:
        raise
    except JWTError as exc:  # pragma: no cover - defensive branch
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    username = payload.get("preferred_username") or payload.get("sub")
    subject = payload.get("sub")
    if not username or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    kc_roles = service.extract_roles(payload)
    role = service.map_role(kc_roles)
    return User(
        subject=subject,
        username=username,
        email=payload.get("email"),
        roles=kc_roles,
        role=role,
    )


ROLE_LEVELS = {
    "user": 0,
    "admin": 10,
}


def require_role(required_role: str):
    """Factory returning a dependency enforcing a minimum application role."""

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


def authorize_action(action: str, resource: Optional[str] = None):
    """Dependency that optionally asks OPA for a fine grained decision."""

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        client = get_opa_client()
        if client is None:
            return current_user
        evaluation = client.evaluate(
            {
                "input": {
                    "subject": {
                        "id": current_user.subject,
                        "username": current_user.username,
                        "roles": list(current_user.roles),
                    },
                    "action": action,
                    "resource": resource,
                }
            }
        )
        decision = evaluation.get("result")
        allowed = False
        if isinstance(decision, dict):
            allowed = bool(decision.get("allow"))
        elif isinstance(decision, bool):
            allowed = decision
        if not allowed:
            detail = "Access denied by policy"
            if isinstance(decision, dict) and decision.get("reason"):
                detail = str(decision["reason"])
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
        return current_user

    return dependency


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def password_grant(username: str, password: str) -> Token:
    """Obtain an access token from Keycloak using the password grant."""

    service = get_keycloak_service()
    return service.obtain_token(username, password)


def refresh_access_token(refresh_token: str) -> Token:
    """Refresh the access token using Keycloak."""

    service = get_keycloak_service()
    return service.refresh_token(refresh_token)


def introspect_access_token(token: str) -> TokenIntrospection:
    """Return the introspection result for the provided access token."""

    service = get_keycloak_service()
    return service.introspect_token(token)
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
