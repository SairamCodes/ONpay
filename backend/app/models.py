from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def now_utc() -> datetime:
    # Store naive UTC values so SQLite and PostgreSQL use the same comparison semantics.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    college: Mapped[str | None] = mapped_column(String(140), nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(180), nullable=True)
    verified_email: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_phone: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[str] = mapped_column(String(16), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class OTPChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    contact: Mapped[str] = mapped_column(String(254), index=True)
    channel: Mapped[str] = mapped_column(String(12))
    intent: Mapped[str] = mapped_column(String(12))
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    college: Mapped[str | None] = mapped_column(String(140), nullable=True)
    code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)  # need / have
    amount_min: Mapped[int] = mapped_column(Integer)
    amount_max: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(180))
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    availability: Mapped[str] = mapped_column(String(120))
    note: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Exchange(Base):
    __tablename__ = "exchanges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), unique=True)
    matched_listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), unique=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(180))
    meetup_at: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="match_found", index=True)
    requester_arrived: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_arrived: Mapped[bool] = mapped_column(Boolean, default=False)
    requester_cash_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_cash_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    participant_a: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    participant_b: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    exchange_id: Mapped[str | None] = mapped_column(ForeignKey("exchanges.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)
    __table_args__ = (UniqueConstraint("participant_a", "participant_b", "exchange_id", name="uq_conversation_pair_exchange"),)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, index=True)


class Friendship(Base):
    __tablename__ = "friendships"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_low: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_high: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    __table_args__ = (UniqueConstraint("user_low", "user_high", name="uq_friendship_pair"),)


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exchange_id: Mapped[str] = mapped_column(ForeignKey("exchanges.id"), index=True)
    payer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    payee_upi: Mapped[str] = mapped_column(String(100))
    amount: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="payment_initiated", index=True)
    provider: Mapped[str] = mapped_column(String(24), default="upi_deep_link")
    provider_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    provider_utr: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    exchange_id: Mapped[str] = mapped_column(ForeignKey("exchanges.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24))
    details: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class PointLedger(Base):
    __tablename__ = "points_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    exchange_id: Mapped[str | None] = mapped_column(ForeignKey("exchanges.id"), nullable=True)
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    __table_args__ = (UniqueConstraint("user_id", "exchange_id", "reason", name="uq_points_award"),)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default="info")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reported_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    exchange_id: Mapped[str | None] = mapped_column(ForeignKey("exchanges.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(60))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Block(Base):
    __tablename__ = "blocks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    blocker_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    blocked_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),)


Index("ix_listing_kind_status_amount", Listing.kind, Listing.status, Listing.amount_min, Listing.amount_max)
