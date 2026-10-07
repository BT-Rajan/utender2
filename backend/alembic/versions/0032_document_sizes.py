"""document sizes

Stage 4.4 follow-up: project_drawings.size_bytes, so providers can see how
large each document is. Recorded on every upload from now on; existing files
are measured from storage here, best-effort (one that can't be read stays
NULL and simply shows no size).

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-07

"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_drawings", sa.Column("size_bytes", sa.Integer(), nullable=True))
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, file_path FROM project_drawings")).fetchall()
    if not rows:
        return
    try:
        from app.services.storage import get_storage

        storage = get_storage()
    except Exception:
        logging.getLogger("alembic").warning("storage unavailable: existing document sizes left unknown")
        return
    for drawing_id, path in rows:
        try:
            content = storage.download("project-drawings", path)
        except Exception:
            content = None
        if content is not None:
            bind.execute(sa.text("UPDATE project_drawings SET size_bytes = :s WHERE id = :i"), {"s": len(content), "i": drawing_id})


def downgrade() -> None:
    op.drop_column("project_drawings", "size_bytes")
