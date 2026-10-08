"""milestones

Stage 7.7: an agreement's deliverables (milestones), evidence linked to one
(agreement_documents.milestone_id), deliverable events in the execution
history (execution_updates.milestone_id), and the milestone_updated
notification.

Downgrade drops them. It is refused while any deliverable exists, unless
ALLOW_MILESTONE_LOSS=1 is set.

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-08

"""
import os

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
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
    "tender_paused", "tender_resumed", "requirement_ended", "clarification_shared",
    "offer_clarification_requested", "offer_clarification_answered", "work_started", "execution_updated",
]
_NEW = ["milestone_updated"]


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.create_table(
        "milestones",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agreement_id", sa.String(36), sa.ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("project_item_id", sa.String(36), sa.ForeignKey("project_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivery_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_milestones_agreement_id", "milestones", ["agreement_id"])
    op.add_column("agreement_documents", sa.Column("milestone_id", sa.String(36), nullable=True))
    op.create_index("ix_agreement_documents_milestone_id", "agreement_documents", ["milestone_id"])
    op.create_foreign_key("fk_agreement_documents_milestone", "agreement_documents", "milestones", ["milestone_id"], ["id"], ondelete="SET NULL")
    op.add_column("execution_updates", sa.Column("milestone_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_execution_updates_milestone", "execution_updates", "milestones", ["milestone_id"], ["id"], ondelete="SET NULL")
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES + _NEW)} NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    held = bind.execute(sa.text("SELECT COUNT(*) FROM milestones")).scalar()
    if held and os.environ.get("ALLOW_MILESTONE_LOSS") != "1":
        raise RuntimeError(f"{held} deliverable(s) would be lost by this downgrade. Set ALLOW_MILESTONE_LOSS=1 to proceed anyway.")
    op.execute("DELETE FROM notifications WHERE type = 'milestone_updated'")
    op.execute("DELETE FROM execution_updates WHERE kind IN ('delivered', 'accepted', 'returned')")
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_TYPES)} NOT NULL")
    op.drop_constraint("fk_execution_updates_milestone", "execution_updates", type_="foreignkey")
    op.drop_column("execution_updates", "milestone_id")
    op.drop_constraint("fk_agreement_documents_milestone", "agreement_documents", type_="foreignkey")
    op.drop_index("ix_agreement_documents_milestone_id", table_name="agreement_documents")
    op.drop_column("agreement_documents", "milestone_id")
    op.drop_table("milestones")
