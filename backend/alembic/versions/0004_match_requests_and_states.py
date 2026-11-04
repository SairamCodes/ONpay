"""Match requests, dual confirmation fields, search radius, and status normalization.

Revision ID: 0004_match_requests_and_states
Revises: 0003_receiver_confirmation_pro
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_match_requests_and_states"
down_revision = "0003_receiver_confirmation_pro"
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

    # 1. Create match_requests table if it doesn't exist
    if "match_requests" not in tables:
        op.create_table(
            "match_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("seeker_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider_id", sa.String(length=36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seeker_listing_id", sa.String(length=36), sa.ForeignKey("listings.id"), nullable=False),
            sa.Column("provider_listing_id", sa.String(length=36), sa.ForeignKey("listings.id"), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("responded_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_match_requests_seeker_id", "match_requests", ["seeker_id"])
        op.create_index("ix_match_requests_provider_id", "match_requests", ["provider_id"])
        op.create_index("ix_match_requests_seeker_listing_id", "match_requests", ["seeker_listing_id"])
        op.create_index("ix_match_requests_provider_listing_id", "match_requests", ["provider_listing_id"])
        op.create_index("ix_match_requests_status", "match_requests", ["status"])
        op.create_index("ix_match_requests_expires_at", "match_requests", ["expires_at"])

    # 2. Add search_radius_km to listings
    listing_cols = _columns("listings")
    if "search_radius_km" not in listing_cols:
        with op.batch_alter_table("listings") as batch_op:
            batch_op.add_column(sa.Column("search_radius_km", sa.Integer(), server_default="10", nullable=False))

    # 3. Add upi_id to users
    user_cols = _columns("users")
    if "upi_id" not in user_cols:
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("upi_id", sa.String(length=100), nullable=True))

    # 4. Add dual confirmation fields to exchanges
    exchange_cols = _columns("exchanges")
    new_exchange_cols = []
    if "seeker_cash_received" not in exchange_cols:
        new_exchange_cols.append(sa.Column("seeker_cash_received", sa.Boolean(), server_default=sa.false(), nullable=False))
    if "seeker_cash_received_at" not in exchange_cols:
        new_exchange_cols.append(sa.Column("seeker_cash_received_at", sa.DateTime(), nullable=True))
    if "provider_upi_received" not in exchange_cols:
        new_exchange_cols.append(sa.Column("provider_upi_received", sa.Boolean(), server_default=sa.false(), nullable=False))
    if "provider_upi_received_at" not in exchange_cols:
        new_exchange_cols.append(sa.Column("provider_upi_received_at", sa.DateTime(), nullable=True))
    if "cancelled_at" not in exchange_cols:
        new_exchange_cols.append(sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    if "dispute_reason" not in exchange_cols:
        new_exchange_cols.append(sa.Column("dispute_reason", sa.String(length=500), nullable=True))

    if new_exchange_cols:
        with op.batch_alter_table("exchanges") as batch_op:
            for col in new_exchange_cols:
                batch_op.add_column(col)

    # 5. Update exchange status values
    status_updates = [
        ("match_found", "MATCH_ACCEPTED"),
        ("awaiting_meetup", "MATCH_ACCEPTED"),
        ("meetup_confirmed", "CASH_HANDOVER_PENDING"),
        ("payment_initiated", "PAYMENT_INITIATED"),
        ("verification_pending", "PAYMENT_PENDING"),
        ("receiver_confirmed", "PAYMENT_VERIFIED"),
        ("success", "COMPLETED"),
        ("cancelled", "CANCELLED"),
        ("expired", "EXPIRED"),
        ("disputed", "DISPUTED"),
    ]
    for old_s, new_s in status_updates:
        op.get_bind().execute(sa.text(f"UPDATE exchanges SET status = '{new_s}' WHERE status = '{old_s}'"))

    # 6. Update payment_attempts status values
    payment_status_updates = [
        ("payment_initiated", "PAYMENT_INITIATED"),
        ("verification_pending", "PAYMENT_PENDING"),
        ("receiver_confirmed", "PAYMENT_VERIFIED"),
        ("success", "COMPLETED"),
        ("cancelled", "CANCELLED"),
        ("failed", "FAILED"),
    ]
    for old_s, new_s in payment_status_updates:
        op.get_bind().execute(sa.text(f"UPDATE payment_attempts SET status = '{new_s}' WHERE status = '{old_s}'"))

    # 7. Rename plus -> membership in users.plan and subscriptions.plan
    op.get_bind().execute(sa.text("UPDATE users SET plan = 'membership' WHERE plan = 'plus'"))
    op.get_bind().execute(sa.text("UPDATE subscriptions SET plan = 'membership' WHERE plan = 'plus'"))


def downgrade() -> None:
    # Downgrade plan names
    op.get_bind().execute(sa.text("UPDATE users SET plan = 'plus' WHERE plan = 'membership'"))
    op.get_bind().execute(sa.text("UPDATE subscriptions SET plan = 'plus' WHERE plan = 'membership'"))

    # Downgrade payment statuses
    payment_status_downgrades = [
        ("PAYMENT_INITIATED", "payment_initiated"),
        ("PAYMENT_PENDING", "verification_pending"),
        ("PAYMENT_VERIFIED", "receiver_confirmed"),
        ("COMPLETED", "success"),
        ("CANCELLED", "cancelled"),
        ("FAILED", "failed"),
    ]
    for new_s, old_s in payment_status_downgrades:
        op.get_bind().execute(sa.text(f"UPDATE payment_attempts SET status = '{old_s}' WHERE status = '{new_s}'"))

    # Downgrade exchange statuses
    status_downgrades = [
        ("MATCH_ACCEPTED", "awaiting_meetup"),
        ("CASH_HANDOVER_PENDING", "meetup_confirmed"),
        ("PAYMENT_INITIATED", "payment_initiated"),
        ("PAYMENT_PENDING", "verification_pending"),
        ("PAYMENT_VERIFIED", "receiver_confirmed"),
        ("COMPLETED", "success"),
        ("CANCELLED", "cancelled"),
        ("EXPIRED", "expired"),
        ("DISPUTED", "disputed"),
    ]
    for new_s, old_s in status_downgrades:
        op.get_bind().execute(sa.text(f"UPDATE exchanges SET status = '{old_s}' WHERE status = '{new_s}'"))

    # Drop exchange columns
    exchange_cols = _columns("exchanges")
    cols_to_drop = [
        "seeker_cash_received", "seeker_cash_received_at",
        "provider_upi_received", "provider_upi_received_at",
        "cancelled_at", "dispute_reason",
    ]
    existing_to_drop = [c for c in cols_to_drop if c in exchange_cols]
    if existing_to_drop:
        with op.batch_alter_table("exchanges") as batch_op:
            for c in existing_to_drop:
                batch_op.drop_column(c)

    # Drop user columns
    user_cols = _columns("users")
    if "upi_id" in user_cols:
        with op.batch_alter_table("users") as batch_op:
            batch_op.drop_column("upi_id")

    # Drop listing columns
    listing_cols = _columns("listings")
    if "search_radius_km" in listing_cols:
        with op.batch_alter_table("listings") as batch_op:
            batch_op.drop_column("search_radius_km")

    # Drop match_requests table
    tables = _tables()
    if "match_requests" in tables:
        op.drop_table("match_requests")
