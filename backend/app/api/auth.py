"""Deliberately minimal MVP auth: email/password with stdlib PBKDF2.
Endpoints return the user id; the frontend keeps it client-side."""

from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    return secrets.compare_digest(hash_password(password, salt), stored)


class SignupRequest(BaseModel):
    email: EmailStr
    name: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str


@router.post("/signup", response_model=UserOut)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(User).where(User.email == req.email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=req.email, name=req.name, password_hash=hash_password(req.password))
    db.add(user)
    await db.commit()
    return UserOut(id=user.id, email=user.email, name=user.name)


@router.post("/login", response_model=UserOut)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(select(User).where(User.email == req.email))
    if user is None or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return UserOut(id=user.id, email=user.email, name=user.name)
