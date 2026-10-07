"""draft save, resume and discard

Stage 3.11. projects gains:
  * updated_at: last saved (also the version a save must match);
  * discarded_at: a draft the owner deliberately discarded (soft);
  * creation_token + unique (owner_id, creation_token): one draft per
    "start a requirement" submission, however often it is sent.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column("discarded_at", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column("creation_token", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_project_creation_token", "projects", ["owner_id", "creation_token"])
    # Existing requirements: last saved = created.
    op.execute("UPDATE projects SET updated_at = created_at WHERE updated_at IS NULL")


def downgrade() -> None:
    op.drop_constraint("uq_project_creation_token", "projects", type_="unique")
    op.drop_column("projects", "creation_token")
    op.drop_column("projects", "discarded_at")
    op.drop_column("projects", "updated_at")
