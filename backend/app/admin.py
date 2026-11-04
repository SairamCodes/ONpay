"""ONPay V2 Admin APIs.

Comprehensive management endpoints for admin authentication, dashboard analytics,
user directory, transaction history, point adjustments, QR management, subscription review,
and audit logs.
"""
from __future__ import annotations

import datetime
import os
import re
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, func, or_, text
from sqlalchemy.orm import Session

from .admin_security import (
    ADMIN_COOKIE_NAME,
    create_admin_session,
    current_admin,
    hash_token,
    verify_password,
)
from .config import settings
from .database import get_db
from .models import (
    AdminAuditLog,
    AdminQRCode,
    AdminSession,
    AdminUser,
    Conversation,
    Exchange,
    Listing,
    Message,
    Notification,
    PointLedger,
    Subscription,
    SubscriptionRequest,
    User,
    UserLoginEvent,
    now_utc,
)
from .storage import storage_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOAD_DIR = settings.get_uploads_dir() / "subscription_proofs"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
QR_UPLOAD_DIR = settings.get_uploads_dir() / "qr_codes"
QR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# In-memory rate limiting: ip/email -> list of failed timestamps
_login_failures: Dict[str, List[datetime.datetime]] = {}


def log_admin_action(
    db: Session,
    admin_id: str,
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    details: str = "",
    request: Optional[Request] = None,
) -> None:
    ip = request.client.host if request and request.client else None
    audit = AdminAuditLog(
        id=secrets.token_hex(18),
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip,
        created_at=now_utc(),
    )
    db.add(audit)
    db.commit()


# --- Pydantic Schemas ---
class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class PointsAdjustRequest(BaseModel):
    amount: int
    reason: str = Field(min_length=2, max_length=120)


class SubscriptionRejectRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=250)


# =====================================================================
# 1. ADMIN AUTHENTICATION
# =====================================================================

@router.post("/auth/login")
def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    key = f"{request.client.host if request.client else 'unknown'}:{payload.email.lower()}"
    now = datetime.datetime.now(datetime.timezone.utc)

    # Rate limiting check (5 failed attempts in 5 minutes)
    failures = [t for t in _login_failures.get(key, []) if now - t < datetime.timedelta(minutes=5)]
    _login_failures[key] = failures
    if len(failures) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 5 minutes before trying again.",
        )

    admin = db.query(AdminUser).filter_by(email=payload.email.lower()).first()
    if not admin or not admin.is_active or not verify_password(payload.password, admin.hashed_password):
        failures.append(now)
        _login_failures[key] = failures
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin email or password",
        )

    # Reset failure counter on success
    _login_failures.pop(key, None)

    token = create_admin_session(response, db, admin)
    log_admin_action(
        db, admin.id, "admin_login", "admin_user", admin.id,
        f"Admin logged in successfully ({admin.email})", request,
    )

    return {
        "admin": {
            "id": admin.id,
            "email": admin.email,
            "full_name": admin.full_name,
            "role": admin.role,
        },
        "token": token,
        "session_token": token,
    }


@router.get("/auth/me")
def admin_me(admin: AdminUser = Depends(current_admin)):
    return {
        "id": admin.id,
        "email": admin.email,
        "full_name": admin.full_name,
        "role": admin.role,
        "created_at": admin.created_at.isoformat(),
        "last_login_at": admin.last_login_at.isoformat() if admin.last_login_at else None,
    }


@router.post("/auth/logout")
def admin_logout(
    request: Request,
    response: Response,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(ADMIN_COOKIE_NAME)

    if token:
        session = db.query(AdminSession).filter_by(token_hash=hash_token(token)).first()
        if session:
            db.delete(session)
            db.commit()

    response.delete_cookie(ADMIN_COOKIE_NAME, path="/", httponly=True)
    log_admin_action(db, admin.id, "admin_logout", "admin_user", admin.id, "Admin logged out", request)
    return {"ok": True}


# =====================================================================
# 2. DASHBOARD ANALYTICS
# =====================================================================

@router.get("/analytics")
def dashboard_analytics(
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    now = now_utc()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Total users
    total_users = db.query(User).count()

    # Total successful daily login events (today)
    total_daily_logins = db.query(UserLoginEvent).filter(UserLoginEvent.login_at >= today_start).count()

    # Unique daily active users (today)
    unique_dau = (
        db.query(func.count(func.distinct(UserLoginEvent.user_id)))
        .filter(UserLoginEvent.login_at >= today_start)
        .scalar()
        or 0
    )

    # Completed transactions & volume
    completed_states = ("COMPLETED", "success", "receiver_confirmed")
    completed_tx_count = db.query(Exchange).filter(Exchange.status.in_(completed_states)).count()
    completed_volume = (
        db.query(func.coalesce(func.sum(Exchange.amount), 0))
        .filter(Exchange.status.in_(completed_states))
        .scalar()
        or 0
    )

    # Total points awarded
    total_points = (
        db.query(func.coalesce(func.sum(PointLedger.amount), 0))
        .filter(PointLedger.amount > 0)
        .scalar()
        or 0
    )

    # Subscriptions
    pending_subs = db.query(SubscriptionRequest).filter_by(status="pending_review").count()
    active_subs = (
        db.query(Subscription)
        .filter(
            Subscription.status == "active",
            or_(Subscription.expires_at.is_(None), Subscription.expires_at > now),
        )
        .count()
    )

    # 14-day login trend for analytics charts
    trend: List[Dict[str, Any]] = []
    for i in range(13, -1, -1):
        day = (today_start - datetime.timedelta(days=i)).date()
        d_start = datetime.datetime.combine(day, datetime.time.min, tzinfo=datetime.timezone.utc)
        d_end = datetime.datetime.combine(day, datetime.time.max, tzinfo=datetime.timezone.utc)

        day_logins = db.query(UserLoginEvent).filter(
            UserLoginEvent.login_at >= d_start, UserLoginEvent.login_at <= d_end
        ).count()
        day_dau = (
            db.query(func.count(func.distinct(UserLoginEvent.user_id)))
            .filter(UserLoginEvent.login_at >= d_start, UserLoginEvent.login_at <= d_end)
            .scalar()
            or 0
        )
        trend.append({
            "date": day.isoformat(),
            "logins": day_logins,
            "unique_users": day_dau,
        })

    return {
        "total_users": total_users,
        "total_successful_daily_logins": total_daily_logins,
        "unique_daily_active_users": int(unique_dau),
        "completed_transactions": completed_tx_count,
        "completed_transaction_volume": int(completed_volume),
        "total_points_awarded": int(total_points),
        "pending_subscriptions": pending_subs,
        "active_subscriptions": active_subs,
        "trend_14d": trend,
    }


# =====================================================================
# 3. USERS MANAGEMENT
# =====================================================================

@router.get("/users")
def list_users(
    q: Optional[str] = Query(None, description="Search by name, email, or phone"),
    plan: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(User)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term),
                User.college.ilike(term),
            )
        )
    if plan:
        query = query.filter(User.plan == plan)

    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for u in rows:
        points = db.query(func.coalesce(func.sum(PointLedger.amount), 0)).filter_by(user_id=u.id).scalar() or 0
        completed = db.query(Exchange).filter(
            Exchange.status.in_(("COMPLETED", "success", "receiver_confirmed")),
            or_(Exchange.requester_id == u.id, Exchange.provider_id == u.id),
        ).count()
        result.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "college": u.college,
            "plan": u.plan,
            "points": int(points),
            "completed_exchanges": completed,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "verified_email": u.verified_email,
            "verified_phone": u.verified_phone,
        })

    return {"total": total, "users": result}


@router.get("/users/{user_id}")
def user_detail(
    user_id: str,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")

    points = db.query(func.coalesce(func.sum(PointLedger.amount), 0)).filter_by(user_id=u.id).scalar() or 0
    recent_points = (
        db.query(PointLedger)
        .filter_by(user_id=u.id)
        .order_by(PointLedger.created_at.desc())
        .limit(20)
        .all()
    )
    recent_logins = (
        db.query(UserLoginEvent)
        .filter_by(user_id=u.id)
        .order_by(UserLoginEvent.login_at.desc())
        .limit(10)
        .all()
    )

    return {
        "user": {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "college": u.college,
            "plan": u.plan,
            "upi_id": u.upi_id,
            "points": int(points),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "verified_email": u.verified_email,
            "verified_phone": u.verified_phone,
        },
        "recent_points": [
            {
                "id": p.id,
                "amount": p.amount,
                "reason": p.reason,
                "created_at": p.created_at.isoformat(),
            }
            for p in recent_points
        ],
        "recent_logins": [
            {
                "id": l.id,
                "login_at": l.login_at.isoformat(),
                "ip_address": l.ip_address,
                "user_agent": l.user_agent,
            }
            for l in recent_logins
        ],
    }


# =====================================================================
# 4. TRANSACTIONS HISTORY
# =====================================================================

@router.get("/transactions")
def list_transactions(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(Exchange)
    if status_filter:
        query = query.filter(Exchange.status == status_filter)

    total = query.count()
    exchanges = query.order_by(Exchange.created_at.desc()).offset(offset).limit(limit).all()

    result = []
    for ex in exchanges:
        req = db.get(User, ex.requester_id)
        prov = db.get(User, ex.provider_id)
        result.append({
            "id": ex.id,
            "amount": ex.amount,
            "status": ex.status,
            "location": ex.location,
            "requester": {
                "id": req.id,
                "full_name": req.full_name,
                "email": req.email,
            } if req else None,
            "provider": {
                "id": prov.id,
                "full_name": prov.full_name,
                "email": prov.email,
            } if prov else None,
            "seeker_cash_received": ex.seeker_cash_received,
            "provider_upi_received": ex.provider_upi_received,
            "created_at": ex.created_at.isoformat(),
            "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        })

    return {"total": total, "transactions": result}


# =====================================================================
# 5. POINTS MANAGEMENT
# =====================================================================

@router.get("/points/ledger")
def points_ledger(
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    total = db.query(PointLedger).count()
    rows = db.query(PointLedger).order_by(PointLedger.created_at.desc()).offset(offset).limit(limit).all()

    items = []
    for r in rows:
        u = db.get(User, r.user_id)
        items.append({
            "id": r.id,
            "user_id": r.user_id,
            "user_name": u.full_name if u else "Unknown",
            "user_email": u.email if u else "—",
            "amount": r.amount,
            "reason": r.reason,
            "exchange_id": r.exchange_id,
            "created_at": r.created_at.isoformat(),
        })

    return {"total": total, "entries": items}


@router.post("/users/{user_id}/points/adjust")
def adjust_user_points(
    user_id: str,
    payload: PointsAdjustRequest,
    request: Request,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    entry = PointLedger(
        id=secrets.token_hex(18),
        user_id=user.id,
        exchange_id=None,
        amount=payload.amount,
        reason=f"admin_adjustment: {payload.reason.strip()}",
        created_at=now_utc(),
    )
    db.add(entry)
    db.commit()

    log_admin_action(
        db, admin.id, "adjust_points", "user", user.id,
        f"Adjusted points by {payload.amount:+d} for {user.email}. Reason: {payload.reason}",
        request,
    )

    new_total = db.query(func.coalesce(func.sum(PointLedger.amount), 0)).filter_by(user_id=user.id).scalar() or 0
    return {"ok": True, "new_balance": int(new_total)}


# =====================================================================
# 6. QR CODE MANAGEMENT
# =====================================================================

@router.get("/qr-codes")
def list_qr_codes(
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    rows = db.query(AdminQRCode).order_by(AdminQRCode.created_at.desc()).all()
    return {
        "qr_codes": [
            {
                "id": q.id,
                "title": q.title,
                "upi_id": q.upi_id,
                "is_active": q.is_active,
                "created_at": q.created_at.isoformat(),
                "image_url": f"/api/admin/qr-codes/{q.id}/image",
            }
            for q in rows
        ]
    }

@router.post("/qr-codes")
async def upload_qr_code(
    title: str = Form("Subscription QR"),
    upi_id: str = Form(...),
    file: UploadFile = File(...),
    request: Request = None,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    data = await file.read()
    qr_path, mime, file_size = storage_service.upload_admin_qr(data, file.filename or "")

    qr_id = secrets.token_hex(18)

    # If first QR code, make it active by default
    has_active = db.query(AdminQRCode).filter_by(is_active=True).first() is not None

    qr = AdminQRCode(
        id=qr_id,
        title=title.strip(),
        upi_id=upi_id.strip(),
        image_path=qr_path,
        mime_type=mime,
        is_active=not has_active,
        uploaded_by=admin.id,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db.add(qr)
    db.commit()

    log_admin_action(
        db, admin.id, "upload_qr_code", "qr_code", qr.id,
        f"Uploaded QR '{qr.title}' for VPA {qr.upi_id}", request,
    )

    return {
        "id": qr.id,
        "title": qr.title,
        "upi_id": qr.upi_id,
        "is_active": qr.is_active,
    }


@router.put("/qr-codes/{qr_id}/activate")
def activate_qr_code(
    qr_id: str,
    request: Request,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    target = db.get(AdminQRCode, qr_id)
    if not target:
        raise HTTPException(404, "QR code not found")

    # Deactivate all others
    db.query(AdminQRCode).update({"is_active": False})
    target.is_active = True
    target.updated_at = now_utc()
    db.commit()

    log_admin_action(
        db, admin.id, "activate_qr_code", "qr_code", target.id,
        f"Activated QR '{target.title}' ({target.upi_id})", request,
    )
    return {"ok": True, "active_qr_id": target.id}


@router.get("/qr-codes/{qr_id}/image")
def get_qr_image(
    qr_id: str,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    qr = db.get(AdminQRCode, qr_id)
    if not qr or not qr.image_path:
        raise HTTPException(404, "QR code image not found")
    return storage_service.get_file_response(qr.image_path, settings.supabase_qr_bucket, qr.mime_type)


# =====================================================================
# 7. SUBSCRIPTION MANAGEMENT
# =====================================================================

@router.get("/subscriptions")
def list_subscription_requests(
    status_filter: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    filt = status_filter or status
    query = db.query(SubscriptionRequest)
    if filt:
        f_norm = filt.lower()
        if f_norm == "pending":
            f_norm = "pending_review"
        query = query.filter(func.lower(SubscriptionRequest.status) == f_norm)

    total = query.count()
    rows = query.order_by(SubscriptionRequest.created_at.desc()).offset(offset).limit(limit).all()

    now = now_utc()
    items = []
    for r in rows:
        u = db.get(User, r.user_id)
        reviewer = db.get(AdminUser, r.reviewed_by) if r.reviewed_by else None
        elapsed = (now - r.created_at).total_seconds() if r.created_at else 0
        is_overdue = elapsed > 20 * 60 and r.status == "pending_review"

        display_status = "PENDING" if r.status == "pending_review" else r.status.upper()
        amount_inr = round(r.amount_paise / 100) if r.amount_paise else 0

        items.append({
            "id": r.id,
            "user_id": r.user_id,
            "user_name": u.full_name if u else "Unknown",
            "user_email": u.email if u else "—",
            "plan_name": r.plan,
            "plan": r.plan,
            "amount": amount_inr,
            "amount_paise": r.amount_paise,
            "upi_ref": r.utr,
            "utr": r.utr,
            "status": display_status,
            "rejection_reason": r.rejection_reason,
            "has_proof": bool(r.proof_path),
            "proof_url": f"/api/admin/subscriptions/{r.id}/proof",
            "target_review_minutes": 20,
            "elapsed_seconds": int(elapsed),
            "is_overdue": is_overdue,
            "review_target_at": r.review_target_at.isoformat() if r.review_target_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reviewed_at": r.updated_at.isoformat() if (r.reviewed_by and r.updated_at) else None,
            "reviewer_name": reviewer.full_name if reviewer else None,
            "user": {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "college": u.college,
            } if u else None,
        })

    return {"total": total, "requests": items, "items": items}


@router.get("/subscriptions/{req_id}/proof")
def get_subscription_proof(
    req_id: str,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    sub_req = db.get(SubscriptionRequest, req_id)
    if not sub_req or not sub_req.proof_path:
        raise HTTPException(404, "Proof image not found")
    return storage_service.get_file_response(sub_req.proof_path, settings.supabase_subscription_bucket, sub_req.mime_type)


@router.post("/subscriptions/{req_id}/approve")
def approve_subscription(
    req_id: str,
    request: Request,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    sub_req = db.get(SubscriptionRequest, req_id)
    if not sub_req:
        raise HTTPException(404, "Subscription request not found")

    # Idempotent: if already approved, return success
    if sub_req.status == "approved":
        return {"ok": True, "already_approved": True}

    if sub_req.status != "pending_review":
        raise HTTPException(409, f"Cannot approve request with status '{sub_req.status}'")

    user = db.get(User, sub_req.user_id)
    if not user:
        raise HTTPException(404, "User account not found")

    now = now_utc()
    sub_req.status = "approved"
    sub_req.reviewed_by = admin.id
    sub_req.updated_at = now

    # Activate existing subscription entitlement system
    sub = db.query(Subscription).filter_by(user_id=user.id).order_by(Subscription.starts_at.desc()).first()
    if not sub:
        sub = Subscription(id=secrets.token_hex(18), user_id=user.id, plan=sub_req.plan)
        db.add(sub)

    sub.plan = sub_req.plan
    sub.status = "active"
    sub.starts_at = now
    sub.expires_at = now + datetime.timedelta(days=30)
    sub.provider_ref = f"manual_upi_{sub_req.utr}"

    # Update user plan
    user.plan = sub_req.plan

    # Create notification for student
    notif = Notification(
        id=secrets.token_hex(18),
        user_id=user.id,
        title="Subscription Activated!",
        body=f"Your payment with UTR {sub_req.utr} was verified. Your {sub_req.plan.capitalize()} plan is now active!",
        kind="subscription",
        created_at=now,
    )
    db.add(notif)
    db.commit()

    log_admin_action(
        db, admin.id, "approve_subscription", "subscription_request", sub_req.id,
        f"Approved {sub_req.plan} subscription for {user.email} (UTR: {sub_req.utr})", request,
    )

    return {"ok": True, "plan": sub_req.plan, "activated_until": sub.expires_at.isoformat()}


@router.post("/subscriptions/{req_id}/reject")
def reject_subscription(
    req_id: str,
    payload: SubscriptionRejectRequest,
    request: Request,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    sub_req = db.get(SubscriptionRequest, req_id)
    if not sub_req:
        raise HTTPException(404, "Subscription request not found")

    if sub_req.status == "rejected":
        return {"ok": True, "already_rejected": True}

    if sub_req.status != "pending_review":
        raise HTTPException(409, f"Cannot reject request with status '{sub_req.status}'")

    user = db.get(User, sub_req.user_id)
    now = now_utc()
    sub_req.status = "rejected"
    sub_req.rejection_reason = payload.reason.strip()
    sub_req.reviewed_by = admin.id
    sub_req.updated_at = now

    if user:
        notif = Notification(
            id=secrets.token_hex(18),
            user_id=user.id,
            title="Subscription Request Declined",
            body=f"Your subscription request (UTR {sub_req.utr}) was declined: {payload.reason.strip()}",
            kind="subscription",
            created_at=now,
        )
        db.add(notif)

    db.commit()

    log_admin_action(
        db, admin.id, "reject_subscription", "subscription_request", sub_req.id,
        f"Rejected subscription for {user.email if user else 'Unknown'} (UTR: {sub_req.utr}). Reason: {payload.reason}",
        request,
    )

    return {"ok": True, "status": "rejected"}


# =====================================================================
# 8. ADMIN AUDIT LOGS
# =====================================================================

@router.get("/audit-logs")
def list_audit_logs(
    action: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    admin: AdminUser = Depends(current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(AdminAuditLog)
    if action:
        query = query.filter(AdminAuditLog.action == action)

    total = query.count()
    rows = query.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit).all()

    items = []
    for r in rows:
        adm = db.get(AdminUser, r.admin_id)
        items.append({
            "id": r.id,
            "admin_name": adm.full_name if adm else "System",
            "admin_email": adm.email if adm else "—",
            "action": r.action,
            "target_type": r.target_type,
            "target_id": r.target_id,
            "details": r.details,
            "ip_address": r.ip_address,
            "created_at": r.created_at.isoformat(),
        })

    return {"total": total, "logs": items}
