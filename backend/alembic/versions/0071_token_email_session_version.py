"""auth tokens bound to an address; per-account session version

- auth_tokens.email: the address a verify/reset link was mailed to. A link is
  only honoured while the account still has that address. Rows issued before
  this revision have none and are refused (their holder requests a new link).
- users.session_version: carried in session tokens; bumping it ends every
  session of the account (done when its sign-in email changes).

Revision ID: 0071
Revises: 0070
Create Date: 2026-10-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("auth_tokens") as batch:
        batch.add_column(sa.Column("email", sa.String(255), nullable=True))
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("session_version")
    with op.batch_alter_table("auth_tokens") as batch:
        batch.drop_column("email")
