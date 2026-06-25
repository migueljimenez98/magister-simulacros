"""Auth — login + me. Single-tenant, no signup endpoint (admin seeds users)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from ..core.limiter import limiter
from ..core.models import User
from ..core.security import create_access_token, verify_password
from .deps import CurrentUser, SessionDep

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, session: SessionDep) -> TokenResponse:
    user = (await session.execute(
        select(User).where(User.email == data.email)
    )).scalar_one_or_none()

    if not user or not user.enabled or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    token = create_access_token(subject=user.id, role=user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        role=user.role,
    )


@router.get("/me")
async def me(user: CurrentUser) -> dict:
    return {"user_id": user.get("sub"), "role": user.get("role")}
