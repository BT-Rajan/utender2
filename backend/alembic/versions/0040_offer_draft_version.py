"""offer draft version

Stage 5.3: offers.draft_version, bumped by every save of an offer draft, so a
save from a page showing an older draft is refused (If-Match) instead of
overwriting newer work.

Revision ID: 0040
Revises: 0039
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("draft_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("offers", "draft_version")
