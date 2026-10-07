"""post-publication control

Stage 3.15:
  * projects.paused_at / pause_reason: the owner paused participation;
  * projects.closed_at: when offers stopped being accepted;
  * projects.material_revision + offers.based_on_material_revision: offers
    made before a material amendment are flagged for the provider to review;
  * project_amendments.material;
  * notifications.type gains tender_paused and tender_resumed.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_TYPES = [
    "document_rejected", "document_approved", "verification_activated", "payment_activated", "payment_failed",
    "payment_override_granted", "payment_override_revoked", "service_provider_suspended", "service_provider_reactivated",
    "owner_verification_activated", "owner_document_rejected", "owner_document_approved", "owner_suspended",
    "owner_reactivated", "document_expiring", "tender_amendment", "drawing_revised", "clarification_asked",
    "clarification_answered", "bid_submitted", "bid_revised", "bid_withdrawn", "deadline_approaching",
    "tender_closed", "evaluation_ready", "award_won", "award_lost", "tender_cancelled", "tender_no_award",
    "project_suspended", "project_reactivated", "offer_suspended", "offer_reactivated",
    "verification_changes_requested", "verification_rejected", "new_requirement",
]
_NEW = ["tender_paused", "tender_resumed"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column("projects", sa.Column("paused_at", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column("pause_reason", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("closed_at", sa.DateTime(), nullable=True))
    op.add_column("projects", sa.Column("material_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("offers", sa.Column("based_on_material_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("project_amendments", sa.Column("material", sa.Boolean(), nullable=False, server_default=sa.false()))
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    op.execute("DELETE FROM notifications WHERE type IN ('tender_paused', 'tender_resumed')")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_column("project_amendments", "material")
    op.drop_column("offers", "based_on_material_revision")
    op.drop_column("projects", "material_revision")
    op.drop_column("projects", "closed_at")
    op.drop_column("projects", "pause_reason")
    op.drop_column("projects", "paused_at")
