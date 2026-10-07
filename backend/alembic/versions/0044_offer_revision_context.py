"""offer revision context

Stage 5.13: a revised offer keeps what each earlier version said in full.
  * offers.submitted_documents: the documents as they stood at the latest
    submission (what the owner receives until the next one);
  * offer_revisions gain declarations_accepted, documents, submitted_at and
    submitted_by.
Offers already submitted take their current documents as submitted.

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-07

"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("submitted_documents", sa.JSON(), nullable=True))
    op.add_column("offer_revisions", sa.Column("declarations_accepted", sa.JSON(), nullable=True))
    op.add_column("offer_revisions", sa.Column("documents", sa.JSON(), nullable=True))
    op.add_column("offer_revisions", sa.Column("submitted_at", sa.DateTime(), nullable=True))
    op.add_column("offer_revisions", sa.Column("submitted_by", sa.String(36), nullable=True))
    bind = op.get_bind()
    offers = bind.execute(sa.text("SELECT id FROM offers WHERE status <> 'draft'")).fetchall()
    for (offer_id,) in offers:
        docs = bind.execute(
            sa.text("SELECT label, file_name, file_path FROM offer_documents WHERE offer_id = :o ORDER BY label"), {"o": offer_id}
        ).fetchall()
        if docs:
            bind.execute(
                sa.text("UPDATE offers SET submitted_documents = :d WHERE id = :o"),
                {"d": json.dumps([{"label": l, "file_name": n, "file_path": p} for l, n, p in docs]), "o": offer_id},
            )


def downgrade() -> None:
    op.drop_column("offer_revisions", "submitted_by")
    op.drop_column("offer_revisions", "submitted_at")
    op.drop_column("offer_revisions", "documents")
    op.drop_column("offer_revisions", "declarations_accepted")
    op.drop_column("offers", "submitted_documents")
