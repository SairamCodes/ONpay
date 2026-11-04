"""ONPay V2: Friend requests, Admin system, Login events, QR codes, and Subscriptions.

Revision ID: 0005_v2_features
Revises: 0004_match_requests_and_states
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_v2_features"
down_revision = "0004_match_requests_and_states"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return set()
    return {column["name"] for column in insp.get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()

    # 1. Add last_login_at to users
    user_cols = _columns("users")
    if "last_login_at" not in user_cols:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))

    # 2. Friend Requests table
    if "friend_requests" not in tables:
        op.create_table(
            "friend_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("sender_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("receiver_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("exchange_id", sa.String(length=36), sa.ForeignKey("exchanges.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("responded_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_friend_requests_sender_id", "friend_requests", ["sender_id"])
        op.create_index("ix_friend_requests_receiver_id", "friend_requests", ["receiver_id"])
        op.create_index("ix_friend_requests_status", "friend_requests", ["status"])

    # 3. Admin Users table
    if "admin_users" not in tables:
        op.create_table(
            "admin_users",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=100), nullable=False),
            sa.Column("role", sa.String(length=32), server_default="admin", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_login_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_admin_users_email", "admin_users", ["email"], unique=True)

    # 4. Admin Sessions table
    if "admin_sessions" not in tables:
        op.create_table(
            "admin_sessions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("admin_id", sa.String(length=36), sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])
        op.create_index("ix_admin_sessions_token_hash", "admin_sessions", ["token_hash"], unique=True)
        op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])

    # 5. Admin Audit Logs table
    if "admin_audit_logs" not in tables:
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("admin_id", sa.String(length=36), sa.ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=False),
            sa.Column("target_id", sa.String(length=64), nullable=True),
            sa.Column("details", sa.Text(), server_default="", nullable=False),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_admin_audit_logs_admin_id", "admin_audit_logs", ["admin_id"])
        op.create_index("ix_admin_audit_logs_action", "admin_audit_logs", ["action"])
        op.create_index("ix_admin_audit_logs_target_type", "admin_audit_logs", ["target_type"])
        op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])

    # 6. User Login Events table
    if "user_login_events" not in tables:
        op.create_table(
            "user_login_events",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("login_at", sa.DateTime(), nullable=False),
            sa.Column("ip_address", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
        )
        op.create_index("ix_user_login_events_user_id", "user_login_events", ["user_id"])
        op.create_index("ix_user_login_events_login_at", "user_login_events", ["login_at"])

    # 7. Admin QR Codes table
    if "admin_qr_codes" not in tables:
        op.create_table(
            "admin_qr_codes",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("title", sa.String(length=100), nullable=False),
            sa.Column("upi_id", sa.String(length=100), nullable=False),
            sa.Column("image_path", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=32), server_default="image/png", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("uploaded_by", sa.String(length=36), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_admin_qr_codes_is_active", "admin_qr_codes", ["is_active"])

    # 8. Subscription Requests table
    if "subscription_requests" not in tables:
        op.create_table(
            "subscription_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("plan", sa.String(length=16), nullable=False),
            sa.Column("amount_paise", sa.Integer(), nullable=False),
            sa.Column("utr", sa.String(length=64), nullable=False),
            sa.Column("proof_path", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=32), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending_review", nullable=False),
            sa.Column("review_target_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_by", sa.String(length=36), sa.ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("rejection_reason", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_subscription_requests_user_id", "subscription_requests", ["user_id"])
        op.create_index("ix_subscription_requests_utr", "subscription_requests", ["utr"], unique=True)
        op.create_index("ix_subscription_requests_status", "subscription_requests", ["status"])
        op.create_index("ix_subscription_requests_review_target_at", "subscription_requests", ["review_target_at"])


def downgrade() -> None:
    tables = _tables()

    tables_to_drop = [
        "subscription_requests",
        "admin_qr_codes",
        "user_login_events",
        "admin_audit_logs",
        "admin_sessions",
        "admin_users",
        "friend_requests",
    ]
    for table in tables_to_drop:
        if table in tables:
            op.drop_table(table)

    user_cols = _columns("users")
    if "last_login_at" in user_cols:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("last_login_at")
