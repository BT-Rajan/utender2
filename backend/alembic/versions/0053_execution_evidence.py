"""execution evidence

Stage 7.9: evidence linked to one progress update
(agreement_documents.execution_update_id). The evidence kinds themselves are
values of the existing kind column.

Downgrade drops the link; the documents stay on the agreement.

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-08

"""
import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agreement_documents", sa.Column("execution_update_id", sa.String(36), nullable=True))
    op.create_index("ix_agreement_documents_execution_update_id", "agreement_documents", ["execution_update_id"])
    op.create_foreign_key("fk_agreement_documents_execution_update", "agreement_documents", "execution_updates", ["execution_update_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_agreement_documents_execution_update", "agreement_documents", type_="foreignkey")
    op.drop_index("ix_agreement_documents_execution_update_id", table_name="agreement_documents")
    op.drop_column("agreement_documents", "execution_update_id")
