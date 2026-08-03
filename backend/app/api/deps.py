"""Shared FastAPI dependencies — DB session, auth, audit graph access."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import async_session
from ..core.models import User
from ..core.security import decode_token

bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncSession:  # type: ignore[return-type]
    async with async_session() as s:
        yield s


SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: SessionDep,
) -> dict[str, Any]:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    try:
        payload = decode_token(creds.credentials)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}") from e

    # Reload the user row so a disabled account is rejected immediately,
    # even within an otherwise valid token window.
    user_id: str = payload.get("sub", "")
    user = (await session.execute(
        select(User).where(User.id == user_id)
    )).scalar_one_or_none()
    if user is None or not user.enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or disabled")

    return payload


CurrentUser = Annotated[dict, Depends(current_user)]


async def actor_label(session: AsyncSession, user: dict[str, Any]) -> str:
    """Human-readable identity for audit trails (level changes, reassignments).
    Falls back to the raw user id if the row is gone."""
    uid = str(user.get("sub") or "")
    if not uid:
        return ""
    row = await session.get(User, uid)
    return (row.email if row else uid)[:255]


def require_role(required: str):
    """Return a FastAPI dependency that enforces a minimum role.

    Usage::

        @router.post("", dependencies=[Depends(require_role("admin"))])

    Roles (in ascending privilege order): "viewer" < "admin".
    Any authenticated token whose `role` claim does not equal `required`
    receives 403 Forbidden. Missing `role` claim is treated as "viewer".
    """
    _ORDER = {"viewer": 0, "admin": 1}

    async def _check(user: CurrentUser) -> dict[str, Any]:
        token_role = (user.get("role") or "viewer").lower()
        if _ORDER.get(token_role, 0) < _ORDER.get(required, 0):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{token_role}' cannot perform this action (requires '{required}')",
            )
        return user

    return _check


def require_any_role(*allowed: str):
    """Return a FastAPI dependency that requires the token role to be in `allowed`.

    Usage::

        @router.post("", dependencies=[Depends(require_any_role("coordinadora", "admin"))])

    Raises 403 if the token's `role` claim is not in the allowed set.
    Missing `role` is treated as "viewer".
    Does NOT affect the existing `require_role` semantics.
    """
    allowed_set = frozenset(r.lower() for r in allowed)

    async def _check(user: CurrentUser) -> dict[str, Any]:
        token_role = (user.get("role") or "viewer").lower()
        if token_role not in allowed_set:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{token_role}' is not allowed for this action "
                f"(allowed: {sorted(allowed_set)})",
            )
        return user

    return _check


def get_audit_graph(request: Request):
    g = getattr(request.app.state, "audit_graph", None)
    if g is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Audit graph not ready")
    return g
