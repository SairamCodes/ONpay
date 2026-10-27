"""Record receiver confirmations and rename the unlimited plan to Pro.

Revision ID: 0003_receiver_confirmation_pro
Revises: 0002_location_otp_plans
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_receiver_confirmation_pro"
down_revision = "0002_location_otp_plans"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "receiver_confirmed_by" not in _columns("payment_attempts"):
        op.add_column("payment_attempts", sa.Column("receiver_confirmed_by", sa.String(length=36), nullable=True))
    if "receiver_confirmed_at" not in _columns("payment_attempts"):
        op.add_column("payment_attempts", sa.Column("receiver_confirmed_at", sa.DateTime(), nullable=True))
    op.get_bind().execute(sa.text("UPDATE users SET plan = 'pro' WHERE plan = 'premium'"))
    op.get_bind().execute(sa.text("UPDATE subscriptions SET plan = 'pro' WHERE plan = 'premium'"))


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE users SET plan = 'premium' WHERE plan = 'pro'"))
    op.get_bind().execute(sa.text("UPDATE subscriptions SET plan = 'premium' WHERE plan = 'pro'"))
    columns = _columns("payment_attempts")
    if {"receiver_confirmed_by", "receiver_confirmed_at"}.intersection(columns):
        with op.batch_alter_table("payment_attempts") as batch_op:
            if "receiver_confirmed_at" in columns:
                batch_op.drop_column("receiver_confirmed_at")
            if "receiver_confirmed_by" in columns:
                batch_op.drop_column("receiver_confirmed_by")
