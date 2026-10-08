"""user deactivation

Stage 9.2: an admin can deactivate one person's account (users.deactivated_at)
without suspending the organisation they act for; memberships and records
stay, so reactivating restores exactly what they had.

Downgrade is refused while any account is deactivated, unless
ALLOW_REACTIVATION=1 is set.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("deactivated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    # The column is the only record of a deactivation: dropping it reactivates those accounts.
    held = op.get_bind().execute(sa.text("SELECT COUNT(*) FROM users WHERE deactivated_at IS NOT NULL")).scalar()
    if held and os.environ.get("ALLOW_REACTIVATION") != "1":
        raise RuntimeError(f"{held} deactivated account(s) would be reactivated by this downgrade. Set ALLOW_REACTIVATION=1 to proceed anyway.")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("deactivated_at")
