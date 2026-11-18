"""Authentication and role/ownership authorization hooks."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request

from app.api.errors import ApiError
from app.config import Settings
from app.persistence.models import TwinRecord


@dataclass(frozen=True)
class AuthenticatedActor:
    actor_id: str
    role: str  # "clinician", "admin", or "readonly"


def _extract_token(request: Request) -> str | None:
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def get_current_actor(request: Request) -> AuthenticatedActor:
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        actor = AuthenticatedActor(actor_id="local-anonymous", role="admin")
        request.state.actor_id = actor.actor_id
        return actor

    token = _extract_token(request)
    if not token:
        raise ApiError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Missing API credentials. Provide X-API-Key or Authorization Bearer token.",
        )

    principal = settings.api_keys.get(token)
    if principal is None:
        raise ApiError(
            status_code=401,
            code="UNAUTHORIZED",
            message="Invalid API credentials.",
        )

    actor = AuthenticatedActor(actor_id=principal.actor_id, role=principal.role)
    request.state.actor_id = actor.actor_id
    return actor


def require_write_role(
    actor: AuthenticatedActor = Depends(get_current_actor),
) -> AuthenticatedActor:
    if actor.role not in {"clinician", "admin"}:
        raise ApiError(
            status_code=403,
            code="FORBIDDEN",
            message="Caller role does not have write permissions for twin state.",
        )
    return actor


def authorize_twin_access(actor: AuthenticatedActor, twin: TwinRecord) -> None:
    """Verify the authenticated actor is allowed to read/interact with this twin."""
    if actor.role == "admin":
        return
    if actor.role == "readonly":
        # Readonly reviewers can inspect demo/clinician twins in read-only mode
        return
    if twin.owner_id != actor.actor_id:
        raise ApiError(
            status_code=403,
            code="FORBIDDEN",
            message="Caller is not authorized to access this twin.",
        )


def authorize_twin_mutation(actor: AuthenticatedActor, twin: TwinRecord) -> None:
    """Verify the authenticated actor is allowed to mutate this twin."""
    if actor.role not in {"clinician", "admin"}:
        raise ApiError(
            status_code=403,
            code="FORBIDDEN",
            message="Caller role does not have permission to update twins.",
        )
    if actor.role != "admin" and twin.owner_id != actor.actor_id:
        raise ApiError(
            status_code=403,
            code="FORBIDDEN",
            message="Caller is not authorized to modify this twin.",
        )
