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
import os

import sqlalchemy as sa
from alembic import context, op

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


def _target_below_drafts() -> bool:
    """Whether this downgrade goes on below 0039 (where draft offers are
    removed): an explicit revision under 0039, base, or a relative step that
    far down from here."""
    target = context.get_revision_argument()
    if target is None:  # `alembic downgrade base` passes no revision
        return True
    target = str(target).strip()
    if target in ("base", "0"):
        return True
    if target.startswith("-") and target[1:].isdigit():
        return int(revision) - int(target[1:]) < 39
    return target.isdigit() and int(target) < 39


def downgrade() -> None:
    # Checked here, before anything is dropped: MySQL can't roll back schema
    # changes, so refusing only at 0039 would leave the database half
    # downgraded (the steps above it already run). Same rule as 0039.
    if _target_below_drafts() and os.environ.get("ALLOW_DRAFT_LOSS") != "1":
        with_work = op.get_bind().execute(sa.text(
            "SELECT COUNT(*) FROM offers WHERE status = 'draft' AND (amount IS NOT NULL OR message IS NOT NULL"
            " OR assumptions IS NOT NULL OR timeline_estimate IS NOT NULL OR item_prices IS NOT NULL OR declarations_accepted IS NOT NULL"
            " OR proposed_start_date IS NOT NULL OR proposed_completion_date IS NOT NULL OR proposed_duration_days IS NOT NULL)"
        )).scalar() or 0
        if with_work:
            raise RuntimeError(
                f"{with_work} offer draft(s) hold providers' unsubmitted work, which a downgrade below 0039 would delete. "
                "Nothing has been changed. Export them first, or set ALLOW_DRAFT_LOSS=1 to proceed."
            )
    op.drop_column("offer_revisions", "submitted_by")
    op.drop_column("offer_revisions", "submitted_at")
    op.drop_column("offer_revisions", "documents")
    op.drop_column("offer_revisions", "declarations_accepted")
    op.drop_column("offers", "submitted_documents")
