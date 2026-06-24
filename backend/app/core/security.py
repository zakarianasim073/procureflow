"""
Procurement Flow Specialist BD — Security & Auth Utilities
JWT creation/validation, password hashing, user dependency injection.
"""

from __future__ import annotations

import jwt
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

security = HTTPBearer(auto_error=False)

# ── Password Hashing (SHA-256 with salt for portability) ─────────────────

def hash_password(password: str) -> str:
    """Hash password with random salt using SHA-256."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${pwd_hash}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt, pwd_hash = hashed.split("$")
        return hashlib.sha256((salt + password).encode()).hexdigest() == pwd_hash
    except (ValueError, AttributeError):
        return False


# ── JWT Tokens ────────────────────────────────────────────────────────────

def create_token(user_id: str, plan: str = "free", extra: Optional[dict] = None) -> str:
    """Create a JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "plan": plan,
        "iat": now,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate JWT token."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Get current authenticated user from JWT token (raises 401 if invalid)."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        payload = decode_token(credentials.credentials)
        return {
            "id": payload["sub"],
            "plan": payload.get("plan", "free"),
            "gpt_quota": 50000,
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """Get current user or return guest (no auth required)."""
    if credentials is None:
        return {"id": "guest", "plan": "demo", "gpt_quota": 10}
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return {"id": "guest", "plan": "demo", "gpt_quota": 10}
