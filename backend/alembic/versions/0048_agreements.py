"""agreements

Stage 7.3: the agreement governing each awarded requirement (agreements, one
per award record) and the documents the parties attach to it
(agreement_documents). Every existing award gets its agreement, "preparing".

Downgrade drops both. It is refused while any agreement has moved on from
"preparing", has a reference or effective date, or has a document, unless
ALLOW_AGREEMENT_LOSS=1 is set.

Revision ID: 0048
Revises: 0047
Create Date: 2026-10-08

"""
import os
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agreements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("award_id", sa.String(36), sa.ForeignKey("award_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="preparing"),
        sa.Column("reference", sa.String(120), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("terminated_at", sa.DateTime(), nullable=True),
        sa.Column("termination_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("award_id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_table(
        "agreement_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("party", sa.String(16), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("uploaded_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agreement_documents_agreement_id", "agreement_documents", ["agreement_id"])

    bind = op.get_bind()
    awards = bind.execute(sa.text("SELECT id, project_id FROM award_records")).fetchall()
    for award_id, project_id in awards:
        bind.execute(
            sa.text("INSERT INTO agreements (id, award_id, project_id, status, version) VALUES (:id, :a, :p, 'preparing', 1)"),
            {"id": str(uuid.uuid4()), "a": award_id, "p": project_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text(
        "SELECT (SELECT COUNT(*) FROM agreement_documents) + (SELECT COUNT(*) FROM agreements"
        " WHERE status <> 'preparing' OR reference IS NOT NULL OR effective_date IS NOT NULL)"
    )).scalar()
    if held and os.environ.get("ALLOW_AGREEMENT_LOSS") != "1":
        raise RuntimeError(f"{held} agreement record(s) or document(s) would be lost by this downgrade. Set ALLOW_AGREEMENT_LOSS=1 to proceed anyway.")
    op.drop_table("agreement_documents")
    op.drop_table("agreements")
