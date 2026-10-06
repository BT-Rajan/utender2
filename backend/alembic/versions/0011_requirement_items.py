"""requirement items and pricing basis

Stage 3.4. A requirement can list the measurable components a provider
prices against (project_items: description, optional quantity and unit,
specification/notes) and states what is to be priced (projects.pricing_basis:
lump_sum = one total for the complete requirement, per_item = a price per
listed item). Existing requirements become lump_sum with no items, which is
exactly how offers have always been priced.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-06

"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "pricing_basis",
            sa.Enum("lump_sum", "per_item", name="pricingbasis"),
            nullable=False,
            server_default="lump_sum",
        ),
    )
    op.create_table(
        "project_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("specification", sa.Text(), nullable=True),
    )
    op.create_index("ix_project_items_project_id", "project_items", ["project_id"])


def downgrade() -> None:
    op.drop_table("project_items")  # takes its index with it (MySQL won't drop an FK's index first)
    op.drop_column("projects", "pricing_basis")
