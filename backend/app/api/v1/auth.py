"""Auth API routes — Multi-tenant authentication with password hashing"""

import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any

from app.core.security import create_token, get_current_user, hash_password, verify_password
from app.schemas.auth import LoginRequest, Token
from app.models.user import User, UserPlan
from app.db.base import get_async_session

router = APIRouter(prefix="/auth", tags=["auth"])

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "z.nasim073@gmail.com").strip()
OWNER_PASSWORD = os.getenv("OWNER_PASSWORD", "").strip()


async def ensure_owner_user(db: AsyncSession) -> User:
    stmt = select(User).where(User.email == OWNER_EMAIL)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    hashed = hash_password(OWNER_PASSWORD) if OWNER_PASSWORD else None

    if user:
        updated = False
        if hashed and not verify_password(OWNER_PASSWORD, user.hashed_password):
            user.hashed_password = hashed
            updated = True
        if user.plan != UserPlan.ENTERPRISE:
            user.plan = UserPlan.ENTERPRISE
            updated = True
        if not user.is_superuser:
            user.is_superuser = True
            updated = True
        if not user.is_active:
            user.is_active = True
            updated = True
        if not user.full_name:
            user.full_name = "Zakaria Nasim"
            updated = True
        if updated:
            await db.commit()
            await db.refresh(user)
        return user

    if not hashed:
        raise HTTPException(
            status_code=500,
            detail="Owner account is not configured. Set OWNER_PASSWORD in backend/.env to bootstrap it.",
        )

    user = User(
        id="owner-zakaria-nasim",
        email=OWNER_EMAIL,
        hashed_password=hashed,
        full_name="Zakaria Nasim",
        plan=UserPlan.ENTERPRISE,
        is_active=True,
        is_superuser=True,
        gpt_quota_limit=500000,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_async_session)):
    """Login with email/password against database users only."""
    await ensure_owner_user(db)
    
    # Try database lookup first
    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    
    if user:
        if not verify_password(req.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid password")
        
        token = create_token(user.id, user.plan.value)
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "plan": user.plan.value,
                "name": user.full_name or user.email.split("@")[0].title(),
            },
        }

    raise HTTPException(status_code=401, detail="Invalid email or password")


@router.post("/register")
async def register(req: LoginRequest, db: AsyncSession = Depends(get_async_session)):
    """Register a new user with email/password."""
    import uuid

    await ensure_owner_user(db)
    
    # Check if email already exists
    stmt = select(User).where(User.email == req.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    
    # Create user
    user_id = str(uuid.uuid4())
    hashed = hash_password(req.password)
    uid = req.email.split("@")[0]
    
    user = User(
        id=user_id,
        email=req.email,
        hashed_password=hashed,
        full_name=uid.title(),
        plan=UserPlan.FREE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    token = create_token(user.id, UserPlan.FREE.value)
    
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "plan": UserPlan.FREE.value,
            "name": user.full_name,
        },
    }


@router.get("/me")
async def get_me(
    user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get current authenticated user info."""
    # Try to get full user from DB
    stmt = select(User).where(User.id == user["id"])
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()
    
    if db_user:
        return {
            "success": True,
            "user": {
                "id": db_user.id,
                "email": db_user.email,
                "name": db_user.full_name,
                "plan": db_user.plan.value,
                "is_active": db_user.is_active,
                "gpt_quota_remaining": db_user.gpt_quota_limit - db_user.gpt_quota_used,
            },
        }
    
    # Fallback to JWT payload
    return {
        "success": True,
        "user": {
            "id": user["id"],
            "plan": user["plan"],
            "gpt_quota_remaining": user.get("gpt_quota", 50000),
        },
    }


@router.post("/change-password")
async def change_password(
    data: Dict[str, str],
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Change password for authenticated user."""
    old_password = data.get("old_password", "")
    new_password = data.get("new_password", "")
    
    if not old_password or not new_password:
        raise HTTPException(status_code=400, detail="Old and new password required")
    
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    stmt = select(User).where(User.id == current_user["id"])
    result = await db.execute(stmt)
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not verify_password(old_password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    db_user.hashed_password = hash_password(new_password)
    await db.commit()
    
    return {"success": True, "message": "Password changed successfully"}
