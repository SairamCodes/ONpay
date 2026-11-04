"""ONPay V2 Admin Security & Cryptographic Utilities.

Provides secure PBKDF2-HMAC-SHA256 password hashing, constant-time verification,
admin session tokens, and admin authentication dependencies.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta
from typing import Tuple

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import AdminSession, AdminUser, now_utc

ADMIN_COOKIE_NAME = "onpay_admin_session"
PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with cryptographically random salt."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${key.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored PBKDF2 hash using constant-time comparison."""
    try:
        parts = hashed.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_key = parts[3]
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(key.hex(), expected_key)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_admin_session(response: Response, db: Session, admin: AdminUser) -> str:
    """Create an admin session, store in db, and set secure HTTP-only cookie."""
    token = secrets.token_urlsafe(40)
    same_site = "lax" if settings.app_env.lower() == "development" else "none"
    secure_cookie = settings.app_env.lower() != "development" or same_site == "none"

    session = AdminSession(
        id=secrets.token_hex(18),
        admin_id=admin.id,
        token_hash=hash_token(token),
        expires_at=now_utc() + timedelta(hours=24),  # 24h admin session
        created_at=now_utc(),
    )
    db.add(session)
    admin.last_login_at = now_utc()
    db.commit()

    response.set_cookie(
        ADMIN_COOKIE_NAME,
        token,
        httponly=True,
        secure=secure_cookie,
        samesite=same_site,
        max_age=24 * 3600,
        path="/",
    )
    return token


def current_admin(
    request: Request,
    db: Session = Depends(get_db),
) -> AdminUser:
    """Authorize admin via Bearer token header or admin HTTP-only cookie."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(ADMIN_COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )

    session = db.query(AdminSession).filter_by(token_hash=hash_token(token)).first()
    if not session or session.expires_at < now_utc():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin session expired or invalid",
        )

    admin = db.get(AdminUser, session.admin_id)
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account inactive or not found",
        )

    return admin
