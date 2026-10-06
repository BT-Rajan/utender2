"""provider response requirements and response content

Stage 3.8.
  * projects.response_requirements (JSON): what providers must submit with
    their price -- completion period / approach required or optional,
    requested documents, declarations to accept. NULL = price only.
  * offers / offer_revisions gain item_prices (per-item rates when the
    requirement is priced per item) and assumptions; offers also keep
    declarations_accepted.
  * offer_documents: files a provider submits against the requested
    documents, keyed by requirement + provider like the offer itself.
  * Money columns move from NUMERIC(12,2) to NUMERIC(15,3): prices are in
    KWD, which has three decimals (fils). Widening only; no values change.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_MONEY = [("offers", "amount"), ("offer_revisions", "amount"), ("award_records", "amount")]


def upgrade() -> None:
    op.add_column("projects", sa.Column("response_requirements", sa.JSON(), nullable=True))
    for table in ("offers", "offer_revisions"):
        op.add_column(table, sa.Column("item_prices", sa.JSON(), nullable=True))
        op.add_column(table, sa.Column("assumptions", sa.Text(), nullable=True))
    op.add_column("offers", sa.Column("declarations_accepted", sa.JSON(), nullable=True))
    for table, column in _MONEY:
        op.alter_column(table, column, type_=sa.Numeric(15, 3), existing_type=sa.Numeric(12, 2), existing_nullable=False)
    op.create_table(
        "offer_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "service_provider_id",
            sa.String(36),
            sa.ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "service_provider_id", "label", name="uq_offer_document_label"),
    )
    op.create_index("ix_offer_documents_project_id", "offer_documents", ["project_id"])
    op.create_index("ix_offer_documents_service_provider_id", "offer_documents", ["service_provider_id"])


def downgrade() -> None:
    op.drop_table("offer_documents")  # takes its indexes with it
    for table, column in _MONEY:
        op.alter_column(table, column, type_=sa.Numeric(12, 2), existing_type=sa.Numeric(15, 3), existing_nullable=False)
    op.drop_column("offers", "declarations_accepted")
    for table in ("offers", "offer_revisions"):
        op.drop_column(table, "assumptions")
        op.drop_column(table, "item_prices")
    op.drop_column("projects", "response_requirements")
