"""Add privacy-rounded listing coordinates and OTP delivery state; rename Pro.

Revision ID: 0002_location_otp_plans
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_location_otp_plans"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "latitude" not in _columns("listings"):
        op.add_column("listings", sa.Column("latitude", sa.Float(), nullable=True))
    if "longitude" not in _columns("listings"):
        op.add_column("listings", sa.Column("longitude", sa.Float(), nullable=True))
    if "delivery_status" not in _columns("otp_challenges"):
        op.add_column("otp_challenges", sa.Column("delivery_status", sa.String(length=16), nullable=False, server_default="pending"))
    op.get_bind().execute(sa.text("UPDATE users SET plan = 'premium' WHERE plan = 'pro'"))
    op.get_bind().execute(sa.text("UPDATE subscriptions SET plan = 'premium' WHERE plan = 'pro'"))


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE users SET plan = 'pro' WHERE plan = 'premium'"))
    op.get_bind().execute(sa.text("UPDATE subscriptions SET plan = 'pro' WHERE plan = 'premium'"))
    if "delivery_status" in _columns("otp_challenges"):
        op.drop_column("otp_challenges", "delivery_status")
    if "longitude" in _columns("listings"):
        op.drop_column("listings", "longitude")
    if "latitude" in _columns("listings"):
        op.drop_column("listings", "latitude")
