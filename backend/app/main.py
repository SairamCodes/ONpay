import base64
import hashlib
import hmac
import json
import logging
import math
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parseaddr
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .config import settings
from .database import Base, engine, get_db
from .models import (
    Block, Conversation, Exchange, Friendship, Listing, LoginSession, Message, Notification,
    OTPChallenge, PaymentAttempt, PointLedger, Report, StatusEvent, Subscription, User, now_utc,
)
from .payment_adapter import YouPIMerchantAdapter, create_upi_intent
from .schemas import (
    AcceptListing, ArrivalUpdate, BlockCreate, CashConfirmation, ListingCreate, ListingUpdate,
    MessageCreate, OTPRequest, OTPVerify, PaymentCreate, ProfileUpdate, ReconciliationRequest, ReportCreate,
)
from .security import COOKIE_NAME, create_session, current_user, hash_otp, hash_value, new_id

app = FastAPI(title="ONPay API", version="0.1.0", description="Student cash exchange coordination API")
logger = logging.getLogger("onpay.auth")
RESEND_EMAILS_URL = "https://api.resend.com/emails"
BREVO_EMAILS_URL = "https://api.brevo.com/v3/smtp/email"
EMAIL_REQUEST_TIMEOUT_SECONDS = 10.0
cors_origins = settings.get_cors_origins()
cors_options = {
    "allow_origins": cors_origins,
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["Accept", "Authorization", "Content-Type", "X-Requested-With"],
    "max_age": 600,
}


@app.on_event("startup")
def startup() -> None:
    if settings.app_env != "development" and settings.dev_otp_mode:
        raise RuntimeError("DEV_OTP_MODE must be false unless APP_ENV=development")
    if settings.app_env != "development" and (settings.secret_key == "development-only-change-me" or len(settings.secret_key) < 32):
        raise RuntimeError("Set a random SECRET_KEY with at least 32 characters outside development mode")
    if settings.app_env != "development" and not cors_origins:
        logger.warning("No frontend origin is configured; cross-origin browser requests will be rejected")
    Base.metadata.create_all(bind=engine)
    logger.info("ONPay API startup complete environment=%s cors_origin_count=%s", settings.app_env, len(cors_origins))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(self), geolocation=(self)"
    return response


def clean_phone(contact: str) -> str:
    value = re.sub(r"[\s()-]", "", contact.strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    digits = re.sub(r"\D", "", value)
    if value.startswith("+") and 10 <= len(digits) <= 15:
        return "+" + digits
    if not value.startswith("+") and len(digits) == 10:
        return "+91" + digits
    raise HTTPException(400, "Enter a valid mobile number with country code")


def normalize_contact(payload: OTPRequest) -> str:
    if payload.channel == "mobile":
        return clean_phone(payload.contact)
    contact = payload.contact.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact):
        raise HTTPException(400, "Enter a valid email address")
    return contact


def send_sms_verify(contact: str, action: str) -> str:
    sid = settings.twilio_account_sid
    token = settings.twilio_auth_token
    service = settings.twilio_verify_service_sid
    if not (sid and token and service):
        raise HTTPException(503, "Mobile OTP delivery is not configured")
    endpoint = f"https://verify.twilio.com/v2/Services/{service}/{action}"
    body = urllib.parse.urlencode({"To": contact, "Channel": "sms"}).encode()
    request = urllib.request.Request(endpoint, data=body, method="POST")
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request.add_header("Authorization", f"Basic {auth}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            verification = json.loads(response.read().decode())
            verification_sid = verification.get("sid")
            if not isinstance(verification_sid, str) or not verification_sid:
                raise RuntimeError("Mobile provider returned no verification reference")
            return verification_sid
    except Exception as exc:
        raise HTTPException(502, "Could not reach the mobile verification provider") from exc


def email_delivery_configuration_error() -> str | None:
    if settings.email_provider not in ("resend", "brevo"):
        return "The configured email provider is not supported"
    api_key = settings.brevo_api_key if settings.email_provider == "brevo" else settings.resend_api_key
    if not api_key.strip():
        provider_name = "Brevo" if settings.email_provider == "brevo" else "Resend"
        return f"Email OTP delivery requires a {provider_name} API key"
    sender_address = parseaddr(settings.email_from)[1]
    if not sender_address or "@" not in sender_address:
        return "Email OTP delivery requires a valid sender address"
    return None


def deliver_otp(channel: str, contact: str, code: str) -> str | None:
    if settings.app_env == "development" and settings.dev_otp_mode:
        return "development-mock"
    if channel == "mobile":
        # Twilio Verify generates and delivers its own code; the local code is not used.
        return send_sms_verify(contact, "Verifications")
    configuration_error = email_delivery_configuration_error()
    if configuration_error:
        raise HTTPException(503, configuration_error)
    subject = "Your ONPay sign-in code"
    text_content = f"Your ONPay verification code is {code}. It expires in {settings.otp_ttl_minutes} minutes."
    if settings.email_provider == "brevo":
        sender_name, sender_address = parseaddr(settings.email_from)
        sender = {"email": sender_address}
        if sender_name:
            sender["name"] = sender_name
        endpoint = BREVO_EMAILS_URL
        headers = {
            "api-key": settings.brevo_api_key.strip(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        body = {
            "sender": sender,
            "to": [{"email": contact}],
            "subject": subject,
            "textContent": text_content,
        }
    else:
        endpoint = RESEND_EMAILS_URL
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key.strip()}",
            "Content-Type": "application/json",
        }
        body = {
            "from": settings.email_from,
            "to": [contact],
            "subject": subject,
            "text": text_content,
        }
    response = httpx.post(
        endpoint,
        headers=headers,
        json=body,
        timeout=EMAIL_REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError as exc:
        provider_name = "Brevo" if settings.email_provider == "brevo" else "Resend"
        raise RuntimeError(f"{provider_name} returned an invalid acceptance response") from exc
    response_id_field = "messageId" if settings.email_provider == "brevo" else "id"
    email_id = result.get(response_id_field) if isinstance(result, dict) else None
    if not isinstance(email_id, str) or not email_id.strip():
        provider_name = "Brevo" if settings.email_provider == "brevo" else "Resend"
        raise RuntimeError(f"{provider_name} returned an invalid acceptance response")
    return email_id


def _record_failed_otp_delivery(db: Session, challenge_id: str) -> None:
    db.rollback()
    challenge = db.get(OTPChallenge, challenge_id)
    if challenge is None:
        raise RuntimeError("OTP challenge disappeared before delivery failure was recorded")
    challenge.delivery_status = "failed"
    challenge.code_hash = None
    challenge.provider_ref = None
    db.commit()


def _log_otp_delivery_failure(
    challenge_id: str, channel: str, exc: Exception, failure: str,
) -> None:
    cause = exc.__cause__ or exc
    provider_status = getattr(cause, "code", None) or getattr(cause, "smtp_code", None)
    if not isinstance(provider_status, int):
        provider_status = getattr(getattr(cause, "response", None), "status_code", None)
    if not isinstance(provider_status, int):
        provider_status = "none"
    logger.warning(
        "OTP delivery failed challenge_id=%s channel=%s provider=%s failure=%s "
        "error_type=%s cause_type=%s provider_status=%s",
        challenge_id, channel, "twilio" if channel == "mobile" else settings.email_provider, failure,
        type(exc).__name__, type(cause).__name__, provider_status,
    )


def _otp_delivery_http_error(channel: str, exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException) and exc.status_code == 503:
        if channel == "mobile":
            detail = "Mobile verification is not configured on this server. Choose Email or contact support."
        else:
            detail = "Email verification is not configured on this server. Choose Mobile or contact support."
        return HTTPException(503, detail)
    channel_name = "mobile" if channel == "mobile" else "email"
    return HTTPException(
        502,
        f"The {channel_name} verification provider could not deliver a code. Please try again later.",
    )


_geocode_cache: dict[tuple[float, float], str] = {}
_geocode_lock = threading.Lock()
_last_geocode_at = 0.0


def reverse_geocode(latitude: float, longitude: float) -> str | None:
    """Return a cached locality name; never expose a precise street address."""
    key = (round(latitude, 3), round(longitude, 3))
    if key in _geocode_cache:
        return _geocode_cache[key]
    if not settings.reverse_geocoder_url.strip():
        logger.warning("Reverse geocoding unavailable reason=provider_not_configured")
        return None
    if not settings.reverse_geocoder_user_agent.strip():
        logger.warning("Reverse geocoding unavailable reason=missing_user_agent")
        return None
    global _last_geocode_at
    with _geocode_lock:
        if key in _geocode_cache:
            return _geocode_cache[key]
        elapsed = time.monotonic() - _last_geocode_at
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        query = urllib.parse.urlencode({"lat": key[0], "lon": key[1], "format": "jsonv2", "zoom": 16, "addressdetails": 1})
        separator = "&" if "?" in settings.reverse_geocoder_url else "?"
        request = urllib.request.Request(f"{settings.reverse_geocoder_url}{separator}{query}")
        request.add_header("User-Agent", settings.reverse_geocoder_user_agent.strip())
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            address = data.get("address", {})
            locality = next((address.get(key) for key in (
                "campus", "university", "college", "school", "neighbourhood", "suburb",
                "city", "town", "village", "municipality", "city_district", "county"
            ) if address.get(key)), None)
            state = address.get("state")
            label = ", ".join(part for part in (locality, state) if part) or data.get("name")
            if label:
                _geocode_cache[key] = str(label)[:180]
                _last_geocode_at = time.monotonic()
                return _geocode_cache[key]
            logger.warning("Reverse geocoding unavailable reason=no_place_name")
        except Exception as exc:
            provider_status = getattr(exc, "code", None)
            if not isinstance(provider_status, int):
                provider_status = "none"
            logger.warning(
                "Reverse geocoding unavailable reason=provider_error error_type=%s status=%s",
                type(exc).__name__, provider_status,
            )
        _last_geocode_at = time.monotonic()
        return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    value = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(min(1, math.sqrt(value)))


PLAN_CATALOG = (
    {"id": "free", "name": "Free", "price_inr": 0, "period": "month", "limit": 5},
    {"id": "plus", "name": "Plus", "price_inr": 199, "period": "month", "limit": 20},
    {"id": "premium", "name": "Premium", "price_inr": 499, "period": "month", "limit": None},
)
IN_PROGRESS_EXCHANGE_STATES = ("match_found", "awaiting_meetup", "meetup_confirmed", "payment_initiated", "verification_pending", "disputed")


def current_month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Use calendar months in India time; database timestamps are naive UTC."""
    current = now or now_utc()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    # India uses a fixed UTC+05:30 offset and does not observe daylight saving time.
    local = current.astimezone(timezone(timedelta(hours=5, minutes=30)))
    start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_local.month == 12:
        end_local = start_local.replace(year=start_local.year + 1, month=1)
    else:
        end_local = start_local.replace(month=start_local.month + 1)
    return (start_local.astimezone(timezone.utc).replace(tzinfo=None),
            end_local.astimezone(timezone.utc).replace(tzinfo=None))


def effective_plan(db: Session, user: User) -> str:
    plan = "premium" if user.plan == "pro" else user.plan
    if plan not in ("free", "plus", "premium"):
        plan = "free"
    if plan in ("plus", "premium"):
        subscription = db.query(Subscription).filter_by(
            user_id=user.id, plan=plan, status="active"
        ).order_by(Subscription.starts_at.desc()).first()
        if not subscription or (subscription.expires_at and subscription.expires_at <= now_utc()):
            if subscription:
                subscription.status = "expired"
            user.plan = "free"
            db.commit()
            return "free"
    if user.plan == "pro":
        user.plan = "premium"
        db.commit()
    return plan


def monthly_usage(db: Session, user_id: str) -> tuple[int, int]:
    start, end = current_month_bounds()
    completed = db.query(Exchange).filter(
        Exchange.status == "success", Exchange.completed_at >= start, Exchange.completed_at < end,
        or_(Exchange.requester_id == user_id, Exchange.provider_id == user_id),
    ).count()
    reserved = db.query(Exchange).filter(
        Exchange.status.in_(IN_PROGRESS_EXCHANGE_STATES),
        or_(Exchange.requester_id == user_id, Exchange.provider_id == user_id),
    ).count()
    return completed, reserved


def user_payload(user: User, db: Session) -> dict:
    points = db.query(func.coalesce(func.sum(PointLedger.amount), 0)).filter_by(user_id=user.id).scalar() or 0
    completed = db.query(Exchange).filter(
        Exchange.status == "success", or_(Exchange.requester_id == user.id, Exchange.provider_id == user.id)
    ).count()
    friends = db.query(Friendship).filter(or_(Friendship.user_low == user.id, Friendship.user_high == user.id)).count()
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone,
        "college": user.college, "location_label": user.location_label, "verified_email": user.verified_email,
        "verified_phone": user.verified_phone, "plan": user.plan, "points": int(points),
        "completed_exchanges": completed, "friends_count": friends,
    }


def notify(db: Session, user_id: str, title: str, body: str, kind: str = "info") -> None:
    db.add(Notification(id=new_id(), user_id=user_id, title=title, body=body, kind=kind))


def create_status_event(db: Session, exchange_id: str, status_name: str, actor_id: str | None, details: str = "") -> None:
    db.add(StatusEvent(id=new_id(), exchange_id=exchange_id, status=status_name, actor_id=actor_id, details=details))


def get_exchange_for_user(db: Session, exchange_id: str, user_id: str) -> Exchange:
    exchange = db.get(Exchange, exchange_id)
    if not exchange or user_id not in (exchange.requester_id, exchange.provider_id):
        raise HTTPException(404, "Exchange not found")
    return exchange


def exchange_payload(db: Session, exchange: Exchange, user_id: str) -> dict:
    other_id = exchange.provider_id if user_id == exchange.requester_id else exchange.requester_id
    other = db.get(User, other_id)
    return {
        "id": exchange.id, "amount": exchange.amount, "location": exchange.location,
        "meetup_at": exchange.meetup_at, "status": exchange.status,
        "requester_id": exchange.requester_id, "provider_id": exchange.provider_id,
        "requester_arrived": exchange.requester_arrived, "provider_arrived": exchange.provider_arrived,
        "requester_cash_confirmed": exchange.requester_cash_confirmed,
        "provider_cash_confirmed": exchange.provider_cash_confirmed,
        "other_user": {"id": other.id, "full_name": other.full_name, "college": other.college} if other else None,
        "created_at": exchange.created_at.isoformat(),
    }


def check_quota(db: Session, user: User) -> None:
    plan = effective_plan(db, user)
    limit = next(item["limit"] for item in PLAN_CATALOG if item["id"] == plan)
    if limit is None:
        return
    completed, reserved = monthly_usage(db, user.id)
    if completed + reserved >= limit:
        raise HTTPException(403, f"Your {plan.title()} plan has {completed} completed exchanges and {reserved} active exchange(s) reserved this month (limit {limit})")


@app.get("/api/health")
def health():
    return {"status": "ok", "environment": settings.app_env}


@app.post("/api/auth/otp/request")
def request_otp(payload: OTPRequest, db: Session = Depends(get_db)):
    contact = normalize_contact(payload)
    user_filter = User.phone == contact if payload.channel == "mobile" else User.email == contact
    existing = db.query(User).filter(user_filter).first()
    recent = db.query(OTPChallenge).filter(
        OTPChallenge.contact == contact,
        OTPChallenge.consumed_at.is_(None),
        OTPChallenge.last_sent_at > now_utc() - timedelta(seconds=settings.otp_resend_seconds),
    ).order_by(OTPChallenge.last_sent_at.desc()).first()
    if recent:
        seconds_left = max(1, settings.otp_resend_seconds - int((now_utc() - recent.last_sent_at).total_seconds()))
        raise HTTPException(429, f"Wait {seconds_left} seconds before requesting another code")

    code = f"{secrets.randbelow(1_000_000):06d}"
    eligible = (payload.intent == "signup" and existing is None) or (payload.intent == "login" and existing is not None)
    challenge = OTPChallenge(
        id=new_id(), contact=contact, channel=payload.channel, intent=payload.intent,
        full_name=(payload.full_name or "").strip() or None, college=(payload.college or "").strip() or None,
        code_hash=hash_otp(code) if eligible else None,
        delivery_status="pending" if eligible else "suppressed",
        expires_at=now_utc() + timedelta(minutes=settings.otp_ttl_minutes),
    )
    challenge_id = challenge.id
    db.add(challenge)
    db.commit()
    if eligible:
        try:
            provider_ref = deliver_otp(payload.channel, contact, code)
        except Exception as exc:
            try:
                _record_failed_otp_delivery(db, challenge_id)
            except Exception as persistence_error:
                db.rollback()
                _log_otp_delivery_failure(challenge_id, payload.channel, persistence_error, "failure_state_persistence")
                raise HTTPException(
                    500, "We could not safely record the verification result. Please try again later.",
                ) from persistence_error
            failure = "configuration" if isinstance(exc, HTTPException) and exc.status_code == 503 else "provider"
            _log_otp_delivery_failure(challenge_id, payload.channel, exc, failure)
            raise _otp_delivery_http_error(payload.channel, exc) from exc

        challenge.delivery_status = "mock" if provider_ref == "development-mock" else "sent"
        challenge.provider_ref = provider_ref if provider_ref != "development-mock" else None
        if payload.channel == "mobile" and settings.app_env != "development":
            challenge.code_hash = None
        try:
            db.commit()
        except Exception as exc:
            try:
                _record_failed_otp_delivery(db, challenge_id)
            except Exception as persistence_error:
                db.rollback()
                _log_otp_delivery_failure(challenge_id, payload.channel, persistence_error, "failure_state_persistence")
                raise HTTPException(
                    500, "We could not safely record the verification result. Please try again later.",
                ) from persistence_error
            _log_otp_delivery_failure(challenge_id, payload.channel, exc, "delivery_state_persistence")
            raise HTTPException(
                502, "The delivery result could not be confirmed. Please request a new code later.",
            ) from exc
    result = {"challenge_id": challenge.id, "expires_in_seconds": settings.otp_ttl_minutes * 60,
              "resend_in_seconds": settings.otp_resend_seconds, "channel": payload.channel,
              "contact": contact, "intent": payload.intent, "accepted": True}
    if settings.app_env == "development" and settings.dev_otp_mode and challenge.delivery_status == "mock":
        result["development_code"] = code
    return result


@app.post("/api/auth/otp/verify")
def verify_otp(payload: OTPVerify, response: Response, db: Session = Depends(get_db)):
    challenge = db.get(OTPChallenge, payload.challenge_id)
    if not challenge or challenge.consumed_at or challenge.expires_at < now_utc():
        raise HTTPException(400, "This verification code has expired. Request a new one.")
    if challenge.delivery_status not in ("sent", "mock"):
        raise HTTPException(400, "That code could not be verified. Check it or request a new one.")
    if challenge.attempts >= settings.otp_max_attempts:
        raise HTTPException(429, "Too many incorrect attempts. Request a new code.")
    challenge.attempts += 1
    verified = False
    if challenge.channel == "mobile" and settings.app_env != "development":
        sid = settings.twilio_verify_service_sid
        if not (sid and settings.twilio_account_sid and settings.twilio_auth_token):
            raise HTTPException(503, "Mobile OTP delivery is not configured")
        endpoint = f"https://verify.twilio.com/v2/Services/{sid}/VerificationCheck"
        body = urllib.parse.urlencode({"To": challenge.contact, "Code": payload.code}).encode()
        request = urllib.request.Request(endpoint, data=body, method="POST")
        auth = base64.b64encode(f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode()).decode()
        request.add_header("Authorization", f"Basic {auth}")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(request, timeout=8) as result:
                verified = json.loads(result.read().decode()).get("status") == "approved"
        except urllib.error.HTTPError as exc:
            if exc.code == 400:
                verified = False
            else:
                db.commit()
                raise HTTPException(502, "Could not verify the code with the mobile provider") from exc
        except Exception as exc:
            db.commit()
            raise HTTPException(502, "Could not verify the code with the mobile provider") from exc
    else:
        verified = bool(challenge.code_hash) and hmac.compare_digest(challenge.code_hash, hash_otp(payload.code))
    if not verified:
        db.commit()
        raise HTTPException(400, "That code could not be verified. Check it or request a new one.")

    user_filter = User.phone == challenge.contact if challenge.channel == "mobile" else User.email == challenge.contact
    user = db.query(User).filter(user_filter).first()
    if challenge.intent == "signup":
        if user:
            raise HTTPException(409, "An account already exists. Choose Login instead.")
        if not challenge.full_name:
            raise HTTPException(400, "Full name is required to create an account")
        user = User(
            id=new_id(), full_name=challenge.full_name, college=challenge.college,
            email=challenge.contact if challenge.channel == "email" else None,
            phone=challenge.contact if challenge.channel == "mobile" else None,
            verified_email=challenge.channel == "email", verified_phone=challenge.channel == "mobile",
        )
        db.add(user)
        db.flush()
        db.add(Subscription(id=new_id(), user_id=user.id, plan="free", status="active", starts_at=now_utc()))
    elif not user:
        raise HTTPException(404, "No account was found for that contact")
    challenge.consumed_at = now_utc()
    db.commit()
    create_session(response, db, user)
    return {"user": user_payload(user, db)}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"user": user_payload(user, db)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        session = db.query(LoginSession).filter_by(token_hash=hash_value(token)).first()
        if session:
            db.delete(session)
            db.commit()
    same_site = settings.session_cookie_samesite
    secure_cookie = settings.app_env != "development" or same_site == "none"
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=secure_cookie, samesite=same_site)
    return {"ok": True}


@app.patch("/api/profile")
def update_profile(payload: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.full_name = payload.full_name.strip()
    user.college = (payload.college or "").strip() or None
    db.commit()
    return {"user": user_payload(user, db)}


@app.post("/api/listings")
def create_listing(payload: ListingCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.amount_max < payload.amount_min:
        raise HTTPException(400, "Maximum amount must be at least the minimum amount")
    active = db.query(Listing).filter_by(owner_id=user.id, kind=payload.kind, status="active").first()
    if active:
        raise HTTPException(409, "You already have an active listing of this type. Pause or cancel it first.")
    if payload.kind == "need" and payload.amount_min != payload.amount_max:
        raise HTTPException(400, "Cash requests use one exact amount")
    listing = Listing(
        id=new_id(), owner_id=user.id, kind=payload.kind,
        amount_min=payload.amount_min, amount_max=payload.amount_max,
        # Round to roughly 100 m before persistence; exact GPS values are never returned.
        latitude=round(payload.latitude, 3) if payload.latitude is not None else None,
        longitude=round(payload.longitude, 3) if payload.longitude is not None else None,
        location=payload.location, availability=payload.availability, note=payload.note,
    )
    db.add(listing)
    db.commit()
    return {"listing": listing_payload(db, listing, user.id)}


def listing_payload(db: Session, listing: Listing, viewer_id: str, distance_km: float | None = None) -> dict:
    owner = db.get(User, listing.owner_id)
    return {
        "id": listing.id, "kind": listing.kind, "amount_min": listing.amount_min,
        "amount_max": listing.amount_max, "location": listing.location,
        "availability": listing.availability, "note": listing.note, "status": listing.status,
        "created_at": listing.created_at.isoformat(),
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
        "owner": {"id": owner.id, "full_name": owner.full_name, "college": owner.college,
                  "verified": owner.verified_email or owner.verified_phone} if owner else None,
        "mine": listing.owner_id == viewer_id,
    }


@app.get("/api/listings")
def get_listings(
    kind: str = "all",
    min_amount: int | None = Query(default=None, ge=0),
    max_amount: int | None = Query(default=None, ge=0),
    availability: str = "",
    location: str = "",
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=25, gt=0, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if kind not in ("all", "need", "have"):
        raise HTTPException(400, "Invalid listing filter")
    if (latitude is None) != (longitude is None):
        raise HTTPException(400, "Latitude and longitude must be supplied together")
    blocked = db.query(Block.blocked_id).filter(Block.blocker_id == user.id)
    blocked_by = db.query(Block.blocker_id).filter(Block.blocked_id == user.id)
    query = db.query(Listing).filter(Listing.status == "active", Listing.owner_id != user.id,
                                     ~Listing.owner_id.in_(blocked), ~Listing.owner_id.in_(blocked_by))
    if kind != "all":
        query = query.filter(Listing.kind == kind)
    if min_amount is not None:
        query = query.filter(Listing.amount_max >= min_amount)
    if max_amount is not None:
        query = query.filter(Listing.amount_min <= max_amount)
    if availability.strip():
        query = query.filter(Listing.availability.ilike(f"%{availability.strip()[:80]}%"))
    if location.strip():
        query = query.filter(Listing.location.ilike(f"%{location.strip()[:120]}%"))
    candidates = query.order_by(Listing.created_at.desc()).limit(1000 if latitude is not None else 100).all()
    distances: dict[str, float] = {}
    if latitude is not None and longitude is not None:
        results = []
        for listing in candidates:
            if listing.latitude is None or listing.longitude is None:
                continue
            distance = haversine_km(latitude, longitude, listing.latitude, listing.longitude)
            if distance <= radius_km:
                results.append(listing)
                distances[listing.id] = distance
    else:
        results = candidates
    my_active = db.query(Listing).filter_by(owner_id=user.id, status="active").all()
    compatible = {item.kind for item in my_active}
    return {"listings": [listing_payload(db, item, user.id, distances.get(item.id)) for item in results],
            "can_match": bool(compatible), "my_active_kinds": sorted(compatible),
            "nearby": latitude is not None, "radius_km": radius_km if latitude is not None else None}


@app.get("/api/my-listings")
def my_listings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.query(Listing).filter_by(owner_id=user.id).order_by(Listing.created_at.desc()).all()
    return {"listings": [listing_payload(db, item, user.id) for item in items]}


@app.patch("/api/listings/{listing_id}")
def update_listing(listing_id: str, payload: ListingUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    listing = db.get(Listing, listing_id)
    if not listing or listing.owner_id != user.id:
        raise HTTPException(404, "Listing not found")
    if listing.status == "matched":
        raise HTTPException(409, "This listing already has a match")
    listing.status = payload.status
    db.commit()
    return {"listing": listing_payload(db, listing, user.id)}


@app.post("/api/listings/{listing_id}/accept")
def accept_listing(listing_id: str, payload: AcceptListing, user: User = Depends(current_user), db: Session = Depends(get_db)):
    target = db.query(Listing).filter_by(id=listing_id).with_for_update().first()
    if not target or target.status != "active" or target.owner_id == user.id:
        raise HTTPException(404, "This listing is no longer available")
    my_kind = "have" if target.kind == "need" else "need"
    own = db.query(Listing).filter_by(owner_id=user.id, kind=my_kind, status="active").with_for_update().first()
    if not own:
        raise HTTPException(409, f"Create an active '{my_kind}' listing before matching")
    if not (target.amount_min <= payload.amount <= target.amount_max and own.amount_min <= payload.amount <= own.amount_max):
        raise HTTPException(400, "Agreed amount must fit both listings")
    # Serialize quota reservations for both people so simultaneous accepts cannot overbook a final slot.
    participants = db.query(User).filter(User.id.in_((user.id, target.owner_id))).order_by(User.id).with_for_update().all()
    participant_by_id = {participant.id: participant for participant in participants}
    check_quota(db, participant_by_id[user.id])
    check_quota(db, participant_by_id[target.owner_id])
    requester = target.owner_id if target.kind == "need" else user.id
    provider = user.id if target.kind == "need" else target.owner_id
    request_listing = target if target.kind == "need" else own
    offer_listing = own if target.kind == "need" else target
    exchange = Exchange(
        id=new_id(), listing_id=request_listing.id, matched_listing_id=offer_listing.id,
        requester_id=requester, provider_id=provider, amount=payload.amount,
        location=target.location, meetup_at=target.availability, status="awaiting_meetup",
    )
    target.status = "matched"
    own.status = "matched"
    db.add(exchange)
    create_status_event(db, exchange.id, "match_found", user.id, "Participants matched on amount and availability")
    create_status_event(db, exchange.id, "awaiting_meetup", user.id, "Participants should agree on the meetup details")
    notify(db, requester, "You found a match", f"A student can exchange ₹{payload.amount} with you.", "match")
    notify(db, provider, "You found a match", f"A student can exchange ₹{payload.amount} with you.", "match")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "This listing was matched by another student just now") from exc
    return {"exchange": exchange_payload(db, exchange, user.id)}


@app.get("/api/exchanges")
def get_exchanges(user: User = Depends(current_user), db: Session = Depends(get_db)):
    exchanges = db.query(Exchange).filter(or_(Exchange.requester_id == user.id, Exchange.provider_id == user.id)).order_by(Exchange.created_at.desc()).all()
    return {"exchanges": [exchange_payload(db, item, user.id) for item in exchanges]}


@app.get("/api/exchanges/{exchange_id}")
def get_exchange(exchange_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    exchange = get_exchange_for_user(db, exchange_id, user.id)
    events = db.query(StatusEvent).filter_by(exchange_id=exchange.id).order_by(StatusEvent.created_at.asc()).all()
    payments = db.query(PaymentAttempt).filter_by(exchange_id=exchange.id).order_by(PaymentAttempt.created_at.desc()).all()
    return {"exchange": exchange_payload(db, exchange, user.id),
            "events": [{"status": event.status, "details": event.details, "created_at": event.created_at.isoformat()} for event in events],
            "payments": [{"id": item.id, "amount": item.amount, "reference": item.reference,
                          "status": item.status, "payee_upi": item.payee_upi,
                          "created_at": item.created_at.isoformat()} for item in payments]}


@app.patch("/api/exchanges/{exchange_id}/arrival")
def update_arrival(exchange_id: str, payload: ArrivalUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    exchange = get_exchange_for_user(db, exchange_id, user.id)
    if exchange.status in ("cancelled", "expired", "success", "disputed"):
        raise HTTPException(409, "This exchange can no longer record arrivals")
    if user.id == exchange.requester_id:
        exchange.requester_arrived = payload.arrived
    else:
        exchange.provider_arrived = payload.arrived
    if exchange.requester_arrived and exchange.provider_arrived and exchange.status == "awaiting_meetup":
        exchange.status = "meetup_confirmed"
        create_status_event(db, exchange.id, "meetup_confirmed", user.id, "Both participants confirmed arrival")
        notify(db, exchange.requester_id, "Meetup confirmed", "Both students confirmed they arrived.", "meetup")
        notify(db, exchange.provider_id, "Meetup confirmed", "Both students confirmed they arrived.", "meetup")
    db.commit()
    return {"exchange": exchange_payload(db, exchange, user.id)}


@app.patch("/api/exchanges/{exchange_id}/cash-confirmation")
def confirm_cash(exchange_id: str, payload: CashConfirmation, user: User = Depends(current_user), db: Session = Depends(get_db)):
    exchange = get_exchange_for_user(db, exchange_id, user.id)
    if exchange.status not in ("meetup_confirmed", "payment_initiated", "verification_pending"):
        raise HTTPException(409, "Confirm arrival before recording a handover")
    if user.id == exchange.requester_id:
        exchange.requester_cash_confirmed = payload.handed_over
    else:
        exchange.provider_cash_confirmed = payload.handed_over
    create_status_event(db, exchange.id, "cash_handover_confirmed" if payload.handed_over else "cash_handover_retracted", user.id,
                        "Physical cash handover confirmation recorded separately from digital payment")
    db.commit()
    return {"exchange": exchange_payload(db, exchange, user.id), "message": "Cash handover recorded; payment status is tracked separately."}


@app.post("/api/exchanges/{exchange_id}/cancel")
def cancel_exchange(exchange_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    exchange = get_exchange_for_user(db, exchange_id, user.id)
    if exchange.status not in ("awaiting_meetup", "meetup_confirmed"):
        raise HTTPException(409, "An exchange with a payment attempt cannot be cancelled here. Use the dispute flow.")
    exchange.status = "cancelled"
    for listing_id in (exchange.listing_id, exchange.matched_listing_id):
        listing = db.get(Listing, listing_id)
        if listing:
            listing.status = "cancelled"
    create_status_event(db, exchange.id, "cancelled", user.id, "Exchange cancelled before payment initiation")
    notify(db, exchange.requester_id if user.id == exchange.provider_id else exchange.provider_id,
           "Exchange cancelled", "The other participant cancelled this exchange.", "exchange")
    db.commit()
    return {"exchange": exchange_payload(db, exchange, user.id)}


@app.post("/api/exchanges/{exchange_id}/dispute")
def dispute_exchange(exchange_id: str, payload: ReportCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    exchange = get_exchange_for_user(db, exchange_id, user.id)
    other_id = exchange.provider_id if user.id == exchange.requester_id else exchange.requester_id
    exchange.status = "disputed"
    db.add(Report(id=new_id(), reporter_id=user.id, reported_user_id=other_id, exchange_id=exchange.id,
                  category=payload.category or "exchange_dispute", details=payload.details))
    create_status_event(db, exchange.id, "disputed", user.id, "Participant requested support review")
    db.commit()
    return {"status": "disputed", "message": "Your report is recorded. Payment remains unverified while it is reviewed."}


@app.post("/api/payments/upi-intent")
def create_payment(payload: PaymentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    exchange = get_exchange_for_user(db, payload.exchange_id, user.id)
    if user.id != exchange.requester_id:
        raise HTTPException(403, "Only the student sending the UPI payment can initiate it")
    if exchange.status not in ("meetup_confirmed", "payment_initiated", "verification_pending"):
        raise HTTPException(409, "Confirm meetup arrival before initiating payment")
    pending = db.query(PaymentAttempt).filter(
        PaymentAttempt.exchange_id == exchange.id,
        PaymentAttempt.status.in_(("payment_initiated", "verification_pending")),
    ).order_by(PaymentAttempt.created_at.desc()).first()
    if pending:
        if pending.payee_upi != payload.payee_upi.strip():
            raise HTTPException(409, "A payment attempt is already pending for this exchange")
        recipient = db.get(User, exchange.provider_id)
        intent = create_upi_intent(payee_upi=pending.payee_upi, payee_name=recipient.full_name,
                                   amount_paise=pending.amount, reference=pending.reference)
        return {"payment": {"id": pending.id, "reference": pending.reference, "amount": pending.amount,
                            "status": pending.status, "upi_uri": intent,
                            "verification_note": "Returning from a UPI app will not mark this payment successful."}}
    try:
        attempt = PaymentAttempt(
            id=new_id(), exchange_id=exchange.id, payer_id=user.id, payee_upi=payload.payee_upi.strip(),
            amount=exchange.amount, reference=f"ON{secrets.token_hex(8).upper()}",
            status="payment_initiated", provider="upi_deep_link",
        )
        recipient = db.get(User, exchange.provider_id)
        intent = create_upi_intent(payee_upi=payload.payee_upi, payee_name=recipient.full_name, amount_paise=exchange.amount,
                                   reference=attempt.reference)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.add(attempt)
    exchange.status = "payment_initiated"
    create_status_event(db, exchange.id, "payment_initiated", user.id, "UPI app intent created; no settlement verification available")
    db.commit()
    return {"payment": {"id": attempt.id, "reference": attempt.reference, "amount": attempt.amount,
                        "status": attempt.status, "upi_uri": intent,
                        "verification_note": "Returning from a UPI app will not mark this payment successful."}}


@app.post("/api/payments/{payment_id}/returned")
def payment_returned(payment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    attempt = db.get(PaymentAttempt, payment_id)
    if not attempt or attempt.payer_id != user.id:
        raise HTTPException(404, "Payment attempt not found")
    if attempt.status == "payment_initiated":
        attempt.status = "verification_pending"
        attempt.updated_at = now_utc()
        exchange = db.get(Exchange, attempt.exchange_id)
        if exchange.status == "payment_initiated":
            exchange.status = "verification_pending"
            create_status_event(db, exchange.id, "verification_pending", user.id,
                                "Returned from the UPI app; settlement remains unverified")
            for participant in (exchange.requester_id, exchange.provider_id):
                notify(db, participant, "Payment verification pending", f"Reference {attempt.reference} has not been verified yet.", "payment")
        db.commit()
    return {"payment": {"id": attempt.id, "reference": attempt.reference, "amount": attempt.amount,
                        "status": attempt.status, "last_updated": attempt.updated_at.isoformat()}}


@app.get("/api/payments/{payment_id}")
def get_payment(payment_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    attempt = db.get(PaymentAttempt, payment_id)
    if not attempt:
        raise HTTPException(404, "Payment attempt not found")
    exchange = db.get(Exchange, attempt.exchange_id)
    if user.id not in (exchange.requester_id, exchange.provider_id):
        raise HTTPException(404, "Payment attempt not found")
    return {"payment": {"id": attempt.id, "reference": attempt.reference, "amount": attempt.amount,
                        "status": attempt.status, "last_updated": attempt.updated_at.isoformat(),
                        "provider_utr": attempt.provider_utr}}


@app.get("/api/transactions")
def transactions(
    status_filter: str = "all",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    allowed = {"all", "success", "in_transit", "failed", "cancelled", "disputed"}
    if status_filter not in allowed:
        raise HTTPException(400, "Invalid transaction filter")
    query = db.query(Exchange).filter(or_(Exchange.requester_id == user.id, Exchange.provider_id == user.id))
    status_map = {"in_transit": ("match_found", "awaiting_meetup", "meetup_confirmed", "payment_initiated", "verification_pending")}
    if status_filter == "in_transit":
        query = query.filter(Exchange.status.in_(status_map[status_filter]))
    elif status_filter != "all":
        query = query.filter(Exchange.status == status_filter)
    rows = query.order_by(Exchange.created_at.desc()).offset(offset).limit(limit + 1).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {"transactions": [exchange_payload(db, item, user.id) for item in page],
            "has_more": has_more, "next_offset": offset + len(page)}


@app.get("/api/chats")
def chats(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.query(Conversation).filter(or_(Conversation.participant_a == user.id, Conversation.participant_b == user.id)).order_by(Conversation.updated_at.desc()).all()
    result = []
    for conversation in items:
        other_id = conversation.participant_b if conversation.participant_a == user.id else conversation.participant_a
        other = db.get(User, other_id)
        last = db.query(Message).filter_by(conversation_id=conversation.id).order_by(Message.created_at.desc()).first()
        result.append({"id": conversation.id, "other_user": {"id": other.id, "full_name": other.full_name, "college": other.college},
                       "exchange_id": conversation.exchange_id, "last_message": last.body if last else "Start the conversation",
                       "updated_at": conversation.updated_at.isoformat()})
    return {"chats": result}


@app.post("/api/chats/with/{other_user_id}/messages")
def send_message(other_user_id: str, payload: MessageCreate, exchange_id: str | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    if other_user_id == user.id or not db.get(User, other_user_id):
        raise HTTPException(404, "Student not found")
    if exchange_id:
        get_exchange_for_user(db, exchange_id, user.id)
    if db.query(Block).filter(or_(and_(Block.blocker_id == user.id, Block.blocked_id == other_user_id),
                                  and_(Block.blocker_id == other_user_id, Block.blocked_id == user.id))).first():
        raise HTTPException(403, "Messaging is unavailable for this student")
    a, b = sorted((user.id, other_user_id))
    conversation = db.query(Conversation).filter_by(participant_a=a, participant_b=b, exchange_id=exchange_id).first()
    if not conversation:
        conversation = Conversation(id=new_id(), participant_a=a, participant_b=b, exchange_id=exchange_id)
        db.add(conversation)
        db.flush()
    message = Message(id=new_id(), conversation_id=conversation.id, sender_id=user.id, body=payload.body)
    conversation.updated_at = now_utc()
    db.add(message)
    notify(db, other_user_id, "New message", f"{user.full_name}: {payload.body[:80]}", "message")
    db.commit()
    return {"chat_id": conversation.id, "message": {"id": message.id, "body": message.body, "sender_id": user.id,
            "created_at": message.created_at.isoformat()}}


@app.get("/api/chats/with/{other_user_id}")
def chat_with(other_user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if other_user_id == user.id or not db.get(User, other_user_id):
        raise HTTPException(404, "Student not found")
    if db.query(Block).filter(or_(and_(Block.blocker_id == user.id, Block.blocked_id == other_user_id),
                                  and_(Block.blocker_id == other_user_id, Block.blocked_id == user.id))).first():
        raise HTTPException(403, "Messaging is unavailable for this student")
    a, b = sorted((user.id, other_user_id))
    conversation = db.query(Conversation).filter_by(participant_a=a, participant_b=b, exchange_id=None).first()
    if not conversation:
        conversation = Conversation(id=new_id(), participant_a=a, participant_b=b)
        db.add(conversation)
        db.commit()
    other = db.get(User, other_user_id)
    messages = db.query(Message).filter_by(conversation_id=conversation.id).order_by(Message.created_at.asc()).limit(500).all()
    return {"id": conversation.id, "other_user": {"id": other.id, "full_name": other.full_name, "college": other.college},
            "messages": [{"id": item.id, "body": item.body, "sender_id": item.sender_id,
                          "created_at": item.created_at.isoformat()} for item in messages]}


@app.get("/api/chats/{conversation_id}")
def chat_detail(conversation_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or user.id not in (conversation.participant_a, conversation.participant_b):
        raise HTTPException(404, "Conversation not found")
    messages = db.query(Message).filter_by(conversation_id=conversation.id).order_by(Message.created_at.asc()).limit(500).all()
    return {"chat_id": conversation.id, "messages": [{"id": item.id, "body": item.body, "sender_id": item.sender_id,
            "created_at": item.created_at.isoformat()} for item in messages]}


@app.get("/api/friends")
def friends(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Friendship).filter(or_(Friendship.user_low == user.id, Friendship.user_high == user.id)).all()
    friend_ids = [row.user_high if row.user_low == user.id else row.user_low for row in rows]
    people = db.query(User).filter(User.id.in_(friend_ids)).all() if friend_ids else []
    return {"friends": [{"id": person.id, "full_name": person.full_name, "college": person.college} for person in people]}


@app.get("/api/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(100).all()
    return {"unread_count": sum(1 for row in rows if row.read_at is None), "notifications": [
        {"id": row.id, "title": row.title, "body": row.body, "kind": row.kind,
         "read_at": row.read_at.isoformat() if row.read_at else None, "created_at": row.created_at.isoformat()} for row in rows]}


@app.patch("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Notification, notification_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    item.read_at = now_utc()
    db.commit()
    return {"ok": True}


@app.get("/api/subscriptions")
def subscriptions(user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = effective_plan(db, user)
    used, reserved = monthly_usage(db, user.id)
    limit = next(item["limit"] for item in PLAN_CATALOG if item["id"] == plan)
    return {"current_plan": plan, "usage": used, "reserved": reserved, "limit": limit,
            "remaining": None if limit is None else max(0, limit - used - reserved),
            "plans": list(PLAN_CATALOG), "billing_configured": False,
            "billing_status": "unavailable"}


@app.post("/api/subscriptions/{plan}/checkout")
def subscription_checkout(plan: str, user: User = Depends(current_user)):
    if plan not in ("plus", "premium"):
        raise HTTPException(400, "Choose Plus or Premium")
    raise HTTPException(503, "Subscription billing is not configured. No plan has been activated.")


@app.get("/api/points")
def points(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(PointLedger).filter_by(user_id=user.id).order_by(PointLedger.created_at.desc()).limit(100).all()
    total = db.query(func.coalesce(func.sum(PointLedger.amount), 0)).filter_by(user_id=user.id).scalar() or 0
    return {"balance": int(total), "entries": [{"amount": row.amount, "reason": row.reason,
            "created_at": row.created_at.isoformat()} for row in rows]}


@app.post("/api/reports")
def report(payload: ReportCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.user_id == user.id or not db.get(User, payload.user_id):
        raise HTTPException(400, "Choose another student to report")
    if payload.exchange_id:
        get_exchange_for_user(db, payload.exchange_id, user.id)
    row = Report(id=new_id(), reporter_id=user.id, reported_user_id=payload.user_id,
                 exchange_id=payload.exchange_id, category=payload.category, details=payload.details)
    db.add(row)
    db.commit()
    return {"report_id": row.id, "status": "received"}


@app.post("/api/blocks")
def block_user(payload: BlockCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if payload.user_id == user.id or not db.get(User, payload.user_id):
        raise HTTPException(400, "Choose another student to block")
    exists = db.query(Block).filter_by(blocker_id=user.id, blocked_id=payload.user_id).first()
    if not exists:
        db.add(Block(id=new_id(), blocker_id=user.id, blocked_id=payload.user_id))
        db.commit()
    return {"blocked": True}


@app.delete("/api/blocks/{other_user_id}")
def unblock_user(other_user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    block = db.query(Block).filter_by(blocker_id=user.id, blocked_id=other_user_id).first()
    if block:
        db.delete(block)
        db.commit()
    return {"blocked": False}


@app.post("/api/internal/reconciliation")
def reconcile_payment(
    payload: ReconciliationRequest,
    reconciliation_key: str = Header(default="", alias="X-Reconciliation-Key"),
    db: Session = Depends(get_db),
):
    """Server-only settlement action for an operator who checked the receiving bank record."""
    if not settings.reconciliation_token:
        raise HTTPException(503, "Independent payment reconciliation is not configured")
    if not hmac.compare_digest(reconciliation_key, settings.reconciliation_token):
        raise HTTPException(401, "Invalid reconciliation credentials")
    if not payload.verified_from_bank_record:
        raise HTTPException(400, "An independent bank record must be checked first")
    attempt = db.get(PaymentAttempt, payload.payment_id)
    if not attempt:
        raise HTTPException(404, "Payment attempt not found")
    exchange = db.get(Exchange, attempt.exchange_id)
    if attempt.amount != exchange.amount:
        raise HTTPException(409, "Payment amount does not match the exchange")
    if not (exchange.requester_cash_confirmed and exchange.provider_cash_confirmed):
        raise HTTPException(409, "Both participants must confirm the cash handover first")
    if attempt.status == "success" and exchange.status == "success":
        return {"status": "success", "duplicate": True}
    if attempt.status not in ("payment_initiated", "verification_pending"):
        raise HTTPException(409, "Payment attempt cannot be reconciled from its current state")
    attempt.status = "success"
    attempt.updated_at = now_utc()
    attempt.provider_utr = payload.utr
    exchange.status = "success"
    exchange.completed_at = now_utc()
    create_status_event(db, exchange.id, "success", None,
                        f"Independently reconciled against a bank record; reference {payload.utr}")
    low, high = sorted((exchange.requester_id, exchange.provider_id))
    if not db.query(Friendship).filter_by(user_low=low, user_high=high).first():
        db.add(Friendship(id=new_id(), user_low=low, user_high=high))
    for participant in (exchange.requester_id, exchange.provider_id):
        awarded = db.query(PointLedger).filter_by(user_id=participant, exchange_id=exchange.id,
                                                   reason="verified_exchange").first()
        if not awarded:
            db.add(PointLedger(id=new_id(), user_id=participant, exchange_id=exchange.id,
                               amount=10, reason="verified_exchange"))
        notify(db, participant, "Exchange completed", "The payment and cash handover were independently confirmed.", "exchange")
    db.commit()
    return {"status": "success", "reference": payload.utr}


@app.post("/api/webhooks/youpi")
async def youpi_webhook(request: Request, db: Session = Depends(get_db)):
    """Record signed YouPI merchant events for review; never marks an exchange paid."""
    secret = settings.youpi_webhook_secret
    if not secret:
        raise HTTPException(503, "YouPI-PG webhook is not configured")
    raw_body = await request.body()
    signature = request.headers.get("X-Gateway-Signature", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid webhook payload") from exc
    delivery_id = request.headers.get("X-Gateway-Delivery-Id") or event.get("deliveryId")
    if not delivery_id:
        raise HTTPException(400, "A delivery ID is required for deduplication")
    reference = event.get("orderId", "")
    attempt = db.query(PaymentAttempt).filter_by(reference=reference).first()
    if not attempt:
        raise HTTPException(404, "Payment reference not found")
    if event.get("event") != "SUCCESS":
        raise HTTPException(400, "Only successful payment events can be submitted for reconciliation")
    if attempt.provider_event_id == delivery_id:
        return {"received": True, "duplicate": True, "status": attempt.status}
    event_amount = event.get("amountPaise")
    try:
        if event_amount is None:
            amount_rupees = Decimal(str(event.get("amount", "0")))
            amount_paise = amount_rupees * 100
            if amount_paise != amount_paise.to_integral_value():
                raise ValueError("fractional paise")
            event_amount = int(amount_paise)
        else:
            event_amount = int(event_amount)
    except (InvalidOperation, TypeError, ValueError):
        event_amount = -1
    if event_amount != attempt.amount:
        raise HTTPException(409, "Provider amount does not match the exchange")
    duplicate = db.query(PaymentAttempt).filter_by(provider_event_id=delivery_id).first()
    if duplicate and duplicate.id != attempt.id:
        return {"received": True, "duplicate": True, "status": duplicate.status}
    attempt.provider_event_id = delivery_id
    attempt.provider = "youpi_merchant_experimental"
    attempt.status = "verification_pending"
    attempt.updated_at = now_utc()
    exchange = db.get(Exchange, attempt.exchange_id)
    exchange.status = "verification_pending"
    create_status_event(db, exchange.id, "verification_pending", None,
        "Signed experimental merchant event received; independent settlement reconciliation is still required")
    db.commit()
    return {"received": True, "status": "verification_pending", "reconciliation_required": True}


@app.get("/api/location/settings")
def location_settings(user: User = Depends(current_user)):
    return {
        "stored_location": user.location_label,
        "privacy": "ONPay stores the campus or meeting label only. Exact coordinates are processed for reverse geocoding and nearby requests, but are not stored in your profile.",
    }


@app.patch("/api/location/settings")
def set_location(payload: dict, user: User = Depends(current_user), db: Session = Depends(get_db)):
    label = str(payload.get("label", "")).strip()
    if len(label) > 180:
        raise HTTPException(400, "Location label is too long")
    # Device coordinates are intentionally not accepted or persisted.
    user.location_label = label or None
    db.commit()
    return {"stored_location": label or None}


@app.get("/api/location/reverse")
def location_reverse(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    user: User = Depends(current_user),
):
    label = reverse_geocode(latitude, longitude)
    if label:
        return {"label": label, "status": "resolved", "attribution": settings.reverse_geocoder_attribution or "Configured location provider"}
    if not settings.reverse_geocoder_url.strip():
        reason = "provider_not_configured"
    elif not settings.reverse_geocoder_user_agent.strip():
        reason = "missing_user_agent"
    else:
        reason = "provider_unavailable"
    return {"label": None, "status": "unavailable", "attribution": None, "reason": reason}


@app.get("/api/help")
def help_content():
    return {"items": [
        {"title": "Meet in a public place", "body": "Choose a staffed campus location and tell someone you trust about your meetup."},
        {"title": "Never share your UPI PIN", "body": "ONPay and other students never need your UPI PIN, password, or banking credentials."},
        {"title": "Payment status", "body": "A payment app returning to ONPay is not proof of settlement. Keep the reference and use in-app support if status is pending."},
    ]}


# Keep CORS outside FastAPI's error middleware so even unhandled 500 responses
# (for example, a schema mismatch during an OTP request) include CORS headers.
fastapi_app = app
app = CORSMiddleware(fastapi_app, **cors_options)
