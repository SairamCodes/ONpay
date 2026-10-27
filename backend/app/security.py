import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import LoginSession, User, now_utc

COOKIE_NAME = "onpay_session"


def new_id() -> str:
    return str(uuid4())


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_otp(value: str) -> str:
    return hmac.new(settings.secret_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session(response: Response, db: Session, user: User) -> None:
    token = secrets.token_urlsafe(40)
    same_site = settings.session_cookie_samesite
    secure_cookie = settings.app_env != "development" or same_site == "none"
    session = LoginSession(
        id=new_id(), user_id=user.id, token_hash=hash_value(token),
        expires_at=now_utc() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.commit()
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=secure_cookie,
        samesite=same_site, max_age=settings.session_ttl_hours * 3600, path="/",
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue")
    session = db.query(LoginSession).filter_by(token_hash=hash_value(token)).first()
    if not session or session.expires_at < now_utc():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Your session has expired")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return user
