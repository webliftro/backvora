"""
Authentication router - login, register, refresh, me.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..config import settings
from ..auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    get_current_user,
)

logger = logging.getLogger("backvora.auth")

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str | None
    is_active: bool


@router.post("/register", response_model=UserResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled",
        )
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=req.email, password_hash=hash_password(req.password), name=req.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(id=user.id, email=user.email, name=user.name, is_active=user.is_active)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[0].strip() or request.client.host
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        logger.warning("LOGIN FAIL | email=%s | reason=user_not_found | ip=%s | time=%s", req.email, ip, datetime.now(timezone.utc).isoformat())
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user.password_hash):
        logger.warning("LOGIN FAIL | email=%s | reason=bad_password | hash_prefix=%s | ip=%s | time=%s", req.email, user.password_hash[:20], ip, datetime.now(timezone.utc).isoformat())
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        logger.warning("LOGIN FAIL | email=%s | reason=account_disabled | ip=%s", req.email, ip)
        raise HTTPException(status_code=403, detail="Account disabled")
    logger.info("LOGIN OK | email=%s | ip=%s | time=%s", req.email, ip, datetime.now(timezone.utc).isoformat())
    return TokenResponse(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    user_id = decode_token(req.refresh_token, "refresh")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return TokenResponse(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id))


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return UserResponse(id=user.id, email=user.email, name=user.name, is_active=user.is_active)
