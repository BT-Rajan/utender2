"""subscription details

Stage 9.6: beside subscription_status, what Stripe last told us -- the
billing interval, a cancellation scheduled for the period end, and when the
last applied Stripe event was created (older events are then ignored, so a
delayed delivery can't roll the state back).

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-08

"""
import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("service_provider_profiles") as batch:
        batch.add_column(sa.Column("subscription_interval", sa.String(16), nullable=True))
        batch.add_column(sa.Column("subscription_cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("subscription_event_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("service_provider_profiles") as batch:
        batch.drop_column("subscription_event_at")
        batch.drop_column("subscription_cancel_at_period_end")
        batch.drop_column("subscription_interval")
