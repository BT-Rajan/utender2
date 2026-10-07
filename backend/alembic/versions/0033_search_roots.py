"""search roots

Search follow-up: the Arabic roots of each requirement's listing text and
scope (services.search_text.roots_of), so a search finds words built on the
same root. Kept in step by models.project.sync_derived; backfilled here.

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

from app.services.search_text import roots_of

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("search_roots", sa.String(600), nullable=True))
    op.add_column("projects", sa.Column("search_scope_roots", sa.Text(), nullable=True))
    bind = op.get_bind()
    for pid, title, trade, area, description in bind.execute(sa.text("SELECT id, title, trade, area, description FROM projects")).fetchall():
        bind.execute(
            sa.text("UPDATE projects SET search_roots = :r, search_scope_roots = :s WHERE id = :i"),
            {"r": (roots_of(" ".join(x for x in (title, trade, area) if x)) or "")[:600] or None, "s": roots_of(description), "i": pid},
        )


def downgrade() -> None:
    op.drop_column("projects", "search_scope_roots")
    op.drop_column("projects", "search_roots")
