"""Authentication proxy endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import KeycloakService, Token, TokenIntrospection, get_keycloak_service

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    token: str


class IntrospectRequest(BaseModel):
    token: str


@router.post("/token", response_model=Token)
def obtain_token(payload: TokenRequest, service: KeycloakService = Depends(get_keycloak_service)) -> Token:
    return service.obtain_token(username=payload.username, password=payload.password)


@router.post("/refresh", response_model=Token)
def refresh_token(payload: RefreshRequest, service: KeycloakService = Depends(get_keycloak_service)) -> Token:
    return service.refresh_token(payload.token)


@router.post("/introspect", response_model=TokenIntrospection)
def introspect_token(
    payload: IntrospectRequest, service: KeycloakService = Depends(get_keycloak_service)
) -> TokenIntrospection:
    return service.introspect_token(payload.token)


__all__ = ["router"]
