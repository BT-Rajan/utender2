"""align the migrated schema with the ORM models

`alembic check` against a MySQL database built from 0001-0006 reported 56
differences from the models. None change behaviour; they are drift between
what the migrations created and what the models declare:

  * 19 columns were created nullable by 0001-0005 (no `nullable=False` next
    to a server default) but the models declare them NOT NULL.
  * 18 indexes carry hand-picked `idx_*` / `uq_*` / MySQL-auto names where the
    models' `index=True` implies `ix_<table>_<column>`. Renamed in place
    (metadata-only in MySQL 8; foreign keys keep working).
  * `project_drawings.project_id` had no explicit index; the model declares one
    (not dropped on downgrade: MySQL makes it the foreign key's backing index).
  * `notifications.type` holds the same 33 values as the model, in a
    different order (0005 appended the owner_* values at the end). MySQL
    compares ENUM definitions positionally, so the order is realigned.

Like 0003/0005/0006 this uses MySQL-specific DDL (MODIFY COLUMN, RENAME INDEX).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-01

"""
from alembic import context, op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


# Timestamp columns created nullable with DEFAULT CURRENT_TIMESTAMP.
_TIMESTAMP_COLUMNS = [
    ("audit_logs", "created_at"),
    ("auth_tokens", "created_at"),
    ("award_records", "created_at"),
    ("clarifications", "created_at"),
    ("cms_content", "updated_at"),
    ("contractor_profiles", "created_at"),
    ("document_requirements", "created_at"),
    ("notifications", "created_at"),
    ("offer_revisions", "recorded_at"),
    ("offers", "created_at"),
    ("offers", "updated_at"),
    ("owner_profiles", "created_at"),
    ("payment_overrides", "created_at"),
    ("project_amendments", "created_at"),
    ("project_drawings", "uploaded_at"),
    ("projects", "created_at"),
    ("reviews", "created_at"),
    ("users", "created_at"),
]

# (table, name created by 0001-0006, name the models imply)
_INDEX_RENAMES = [
    ("audit_logs", "idx_audit_logs_action", "ix_audit_logs_action"),
    ("audit_logs", "idx_audit_logs_target", "ix_audit_logs_target_id"),
    ("auth_tokens", "idx_auth_tokens_user", "ix_auth_tokens_user_id"),
    ("auth_tokens", "uq_auth_tokens_hash", "ix_auth_tokens_token_hash"),
    ("clarifications", "idx_clarifications_project", "ix_clarifications_project_id"),
    ("cms_content", "idx_cms_content_key", "ix_cms_content_key"),
    ("contractor_documents", "idx_contractor_documents_contractor", "ix_contractor_documents_contractor_id"),
    ("notifications", "idx_notifications_user", "ix_notifications_user_id"),
    ("offer_revisions", "idx_offer_revisions_offer", "ix_offer_revisions_offer_id"),
    ("offers", "idx_offers_contractor", "ix_offers_contractor_id"),
    ("offers", "idx_offers_project", "ix_offers_project_id"),
    ("owner_documents", "idx_owner_documents_owner", "ix_owner_documents_owner_id"),
    ("payment_overrides", "idx_payment_overrides_contractor", "ix_payment_overrides_contractor_id"),
    ("project_amendments", "idx_project_amendments_project", "ix_project_amendments_project_id"),
    ("projects", "idx_projects_owner", "ix_projects_owner_id"),
    ("projects", "idx_projects_status", "ix_projects_status"),
    ("revoked_tokens", "idx_revoked_tokens_expires_at", "ix_revoked_tokens_expires_at"),
    ("users", "email", "ix_users_email"),  # `email` is MySQL's auto-name for 0001's unique=True
]

# notifications.type — same values both ways, only the order differs.
_NOTIFICATION_TYPES_BEFORE = (
    "'document_rejected','document_approved','verification_activated','payment_activated',"
    "'payment_failed','payment_override_granted','payment_override_revoked','contractor_suspended',"
    "'contractor_reactivated','document_expiring','tender_amendment','drawing_revised',"
    "'clarification_asked','clarification_answered','bid_submitted','bid_revised','bid_withdrawn',"
    "'deadline_approaching','tender_closed','evaluation_ready','award_won','award_lost',"
    "'tender_cancelled','tender_no_award','owner_verification_activated','owner_document_rejected',"
    "'owner_document_approved','owner_suspended','owner_reactivated','project_suspended',"
    "'project_reactivated','offer_suspended','offer_reactivated'"
)
_NOTIFICATION_TYPES_AFTER = (
    "'document_rejected','document_approved','verification_activated','payment_activated',"
    "'payment_failed','payment_override_granted','payment_override_revoked','contractor_suspended',"
    "'contractor_reactivated','owner_verification_activated','owner_document_rejected',"
    "'owner_document_approved','owner_suspended','owner_reactivated','document_expiring',"
    "'tender_amendment','drawing_revised','clarification_asked','clarification_answered',"
    "'bid_submitted','bid_revised','bid_withdrawn','deadline_approaching','tender_closed',"
    "'evaluation_ready','award_won','award_lost','tender_cancelled','tender_no_award',"
    "'project_suspended','project_reactivated','offer_suspended','offer_reactivated'"
)


def upgrade() -> None:
    # NOT NULL. Backfill first: a NULL here would make the ALTER fail under
    # MySQL's strict mode. The backfill value is exactly what the column
    # default would have produced for a normally-inserted row.
    for table, column in _TIMESTAMP_COLUMNS:
        op.execute(f"UPDATE {table} SET {column} = CURRENT_TIMESTAMP WHERE {column} IS NULL")
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(),
            existing_server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        )
    op.execute("UPDATE contractor_profiles SET avg_rating = 0 WHERE avg_rating IS NULL")
    op.alter_column(
        "contractor_profiles",
        "avg_rating",
        existing_type=sa.Numeric(2, 1),
        existing_server_default=sa.text("0"),
        nullable=False,
    )

    for table, old, new in _INDEX_RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME INDEX {old} TO {new}")

    # Guarded so upgrade -> downgrade -> upgrade is repeatable: downgrade()
    # intentionally leaves this index behind (see there).
    # (Offline `--sql` mode has no connection to inspect, so it always emits it.)
    existing = (
        set()
        if context.is_offline_mode()
        else {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("project_drawings")}
    )
    if "ix_project_drawings_project_id" not in existing:
        op.create_index("ix_project_drawings_project_id", "project_drawings", ["project_id"])

    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type ENUM({_NOTIFICATION_TYPES_AFTER}) NOT NULL")


def downgrade() -> None:
    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type ENUM({_NOTIFICATION_TYPES_BEFORE}) NOT NULL")

    # ix_project_drawings_project_id is deliberately NOT dropped here. Once it
    # exists, MySQL adopts it as the backing index for the project_id foreign
    # key (replacing the implicit one), so DROP INDEX fails with error 1553.
    # Keeping an extra index on a foreign-key column is harmless.

    for table, old, new in _INDEX_RENAMES:
        op.execute(f"ALTER TABLE {table} RENAME INDEX {new} TO {old}")

    op.alter_column(
        "contractor_profiles",
        "avg_rating",
        existing_type=sa.Numeric(2, 1),
        existing_server_default=sa.text("0"),
        nullable=True,
    )
    for table, column in _TIMESTAMP_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.DateTime(),
            existing_server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        )
