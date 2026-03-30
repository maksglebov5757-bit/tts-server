from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional

from fastapi import Request

from core.errors import ForbiddenError, UnauthorizedError
from server.bootstrap import ServerSettings


AUTH_MODE_OFF = "off"
AUTH_MODE_STATIC_BEARER = "static_bearer"
LOCAL_DEFAULT_PRINCIPAL_ID = "local-default"
LOCAL_DEFAULT_SUBJECT_TYPE = "local_default"
STATIC_TOKEN_SUBJECT_TYPE = "static_token"
PROTECTED_ROUTE_PREFIXES = (
    "/api/v1/models",
    "/api/v1/tts",
    "/v1/audio/speech",
    "/health/ready",
)
PUBLIC_ROUTE_PATHS = {"/health/live"}


@dataclass(frozen=True)
class RequestPrincipal:
    principal_id: str
    subject_type: str
    authenticated: bool
    credential_id: Optional[str] = None



def build_local_default_principal() -> RequestPrincipal:
    return RequestPrincipal(
        principal_id=LOCAL_DEFAULT_PRINCIPAL_ID,
        subject_type=LOCAL_DEFAULT_SUBJECT_TYPE,
        authenticated=False,
        credential_id=None,
    )



def is_public_route(path: str) -> bool:
    return path in PUBLIC_ROUTE_PATHS



def is_protected_route(path: str) -> bool:
    if is_public_route(path):
        return False
    return any(path.startswith(prefix) for prefix in PROTECTED_ROUTE_PREFIXES)



def resolve_request_principal(request: Request) -> RequestPrincipal:
    settings: ServerSettings = request.app.state.settings
    if settings.auth_mode == AUTH_MODE_OFF:
        return build_local_default_principal()
    if settings.auth_mode != AUTH_MODE_STATIC_BEARER:
        raise UnauthorizedError(reason=f"Unsupported auth mode: {settings.auth_mode}")
    if not is_protected_route(request.url.path):
        return build_local_default_principal()
    return authenticate_static_bearer(request, settings)



def authenticate_static_bearer(request: Request, settings: ServerSettings) -> RequestPrincipal:
    token = extract_bearer_token(request)
    configured_token = settings.auth_static_bearer_token
    if configured_token is None:
        raise UnauthorizedError(reason="Static bearer auth is enabled but no token is configured")
    if token is None:
        raise UnauthorizedError(reason="Missing bearer token")
    if token != configured_token:
        raise UnauthorizedError(reason="Bearer token is invalid")
    credential_id = settings.auth_static_bearer_credential_id or build_credential_id(token)
    principal_id = settings.auth_static_bearer_principal_id or credential_id
    return RequestPrincipal(
        principal_id=principal_id,
        subject_type=STATIC_TOKEN_SUBJECT_TYPE,
        authenticated=True,
        credential_id=credential_id,
    )



def extract_bearer_token(request: Request) -> Optional[str]:
    authorization = request.headers.get("authorization")
    if authorization is None:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        raise UnauthorizedError(reason="Authorization header must use Bearer authentication")
    return credentials.strip()



def ensure_job_owner_access(request: Request, *, owner_principal_id: str) -> None:
    principal: RequestPrincipal = request.state.principal
    if principal.principal_id != owner_principal_id:
        raise ForbiddenError(
            reason="Authenticated principal is not allowed to access this job",
            details={"owner_principal_id": owner_principal_id},
        )



def build_credential_id(token: str) -> str:
    return f"static-bearer-{hashlib.sha256(token.encode('utf-8')).hexdigest()[:16]}"


__all__ = [
    "AUTH_MODE_OFF",
    "AUTH_MODE_STATIC_BEARER",
    "LOCAL_DEFAULT_PRINCIPAL_ID",
    "LOCAL_DEFAULT_SUBJECT_TYPE",
    "RequestPrincipal",
    "STATIC_TOKEN_SUBJECT_TYPE",
    "build_local_default_principal",
    "ensure_job_owner_access",
    "is_protected_route",
    "is_public_route",
    "resolve_request_principal",
]
