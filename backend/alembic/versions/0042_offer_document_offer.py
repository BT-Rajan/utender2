"""offer document offer

Stage 5.6: an offer document belongs to its side's offer (offer_id), and
records the requirement version it was supplied against and who supplied
it. Existing documents are linked to their side's offer, at that offer's
version.

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offer_documents", sa.Column("offer_id", sa.String(36), nullable=True))
    op.add_column("offer_documents", sa.Column("material_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("offer_documents", sa.Column("uploaded_by", sa.String(36), nullable=True))
    op.create_index("ix_offer_documents_offer_id", "offer_documents", ["offer_id"])
    op.create_foreign_key("fk_offer_documents_offer", "offer_documents", "offers", ["offer_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_offer_documents_uploaded_by", "offer_documents", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")
    bind = op.get_bind()
    docs = bind.execute(sa.text("SELECT id, project_id, service_provider_id, organization_id FROM offer_documents")).fetchall()
    for doc_id, project_id, provider_id, organization_id in docs:
        if organization_id:
            row = bind.execute(
                sa.text("SELECT id, based_on_material_revision FROM offers WHERE project_id = :p AND organization_id = :o"),
                {"p": project_id, "o": organization_id},
            ).first()
        else:
            row = bind.execute(
                sa.text("SELECT id, based_on_material_revision FROM offers WHERE project_id = :p AND service_provider_id = :s AND organization_id IS NULL"),
                {"p": project_id, "s": provider_id},
            ).first()
        if row:
            bind.execute(
                sa.text("UPDATE offer_documents SET offer_id = :i, material_revision = :r WHERE id = :d"),
                {"i": row[0], "r": row[1] or 0, "d": doc_id},
            )


def downgrade() -> None:
    op.drop_constraint("fk_offer_documents_uploaded_by", "offer_documents", type_="foreignkey")
    op.drop_constraint("fk_offer_documents_offer", "offer_documents", type_="foreignkey")
    op.drop_index("ix_offer_documents_offer_id", table_name="offer_documents")
    op.drop_column("offer_documents", "uploaded_by")
    op.drop_column("offer_documents", "material_revision")
    op.drop_column("offer_documents", "offer_id")
