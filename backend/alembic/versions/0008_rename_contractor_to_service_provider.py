"""rename contractor -> service provider throughout the schema and data

The marketplace's supply side is called "service provider" everywhere — UI,
API, code and now the database. This migration renames, in place and without
copying any data:

  * tables:  contractor_profiles  -> service_provider_profiles
             contractor_documents -> service_provider_documents
  * columns: contractor_id -> service_provider_id on offers, payment_overrides,
             service_provider_documents, clarifications, reviews, award_records
  * indexes / unique constraints that carry the old name
  * enum values: users.role and document_requirements.applies_to
             ('contractor' -> 'service_provider'); notifications.type
             (contractor_suspended/_reactivated -> service_provider_*)
  * stored strings that the app matches on: audit_logs.action/target_type and
             the in-app links saved on notifications
  * local file storage: the documents folder is renamed to match the new
             logical bucket name (S3 deployments map that name to
             S3_BUCKET_DOCUMENTS, so nothing moves there).

Every ENUM is widened first, rows are rewritten, then the old value is
dropped, so no row ever holds a value its column can't represent. Foreign
keys follow renamed tables/columns automatically in MySQL 8 / MariaDB 10.5+.
Like 0003/0005-0007 this uses MySQL-specific DDL.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-06

"""
from pathlib import Path

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

OLD, NEW = "contractor", "service_provider"

_TABLES = [("contractor_profiles", "service_provider_profiles"), ("contractor_documents", "service_provider_documents")]

# Tables (post-rename names) whose contractor_id column is renamed.
_ID_COLUMN_TABLES = ["offers", "payment_overrides", "service_provider_documents", "clarifications", "reviews", "award_records"]

# (table, old index name, new index name) -- explicit model names plus the
# ix_<table>_<column> names 0007 settled on, plus the MySQL-generated names of
# the foreign-key backing indexes (named after the column).
_INDEXES = [
    ("service_provider_documents", "uq_contractor_requirement", "uq_service_provider_requirement"),
    ("service_provider_documents", "ix_contractor_documents_contractor_id", "ix_service_provider_documents_service_provider_id"),
    ("offers", "uq_project_contractor", "uq_project_service_provider"),
    ("offers", "ix_offers_contractor_id", "ix_offers_service_provider_id"),
    ("payment_overrides", "ix_payment_overrides_contractor_id", "ix_payment_overrides_service_provider_id"),
    ("clarifications", "contractor_id", "service_provider_id"),
    ("reviews", "contractor_id", "service_provider_id"),
    ("award_records", "contractor_id", "service_provider_id"),
]

_NOTIFICATION_TYPES = [
    "document_rejected", "document_approved", "verification_activated", "payment_activated", "payment_failed",
    "payment_override_granted", "payment_override_revoked", "{p}_suspended", "{p}_reactivated",
    "owner_verification_activated", "owner_document_rejected", "owner_document_approved", "owner_suspended",
    "owner_reactivated", "document_expiring", "tender_amendment", "drawing_revised", "clarification_asked",
    "clarification_answered", "bid_submitted", "bid_revised", "bid_withdrawn", "deadline_approaching",
    "tender_closed", "evaluation_ready", "award_won", "award_lost", "tender_cancelled", "tender_no_award",
    "project_suspended", "project_reactivated", "offer_suspended", "offer_reactivated",
]

_OLD_PATH, _NEW_PATH = "contractor", "service-provider"
_OLD_BUCKET, _NEW_BUCKET = "contractor-documents", "service-provider-documents"


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def _notification_types(prefix: str, extra: str | None = None) -> list[str]:
    values = [v.format(p=prefix) for v in _NOTIFICATION_TYPES]
    if extra:
        values += [v.format(p=extra) for v in _NOTIFICATION_TYPES if "{p}" in v]
    return values


def _swap_enums(src: str, dst: str) -> None:
    roles_both = ["owner", src, "admin", dst]
    # users.role
    op.execute(f"ALTER TABLE users MODIFY COLUMN role {_enum(roles_both)} NOT NULL DEFAULT 'owner'")
    op.execute(f"UPDATE users SET role = '{dst}' WHERE role = '{src}'")
    op.execute(f"ALTER TABLE users MODIFY COLUMN role {_enum(['owner', dst, 'admin'])} NOT NULL DEFAULT 'owner'")
    # document_requirements.applies_to
    op.execute(f"ALTER TABLE document_requirements MODIFY COLUMN applies_to {_enum(roles_both)} NOT NULL DEFAULT '{src}'")
    op.execute(f"UPDATE document_requirements SET applies_to = '{dst}' WHERE applies_to = '{src}'")
    op.execute(
        f"ALTER TABLE document_requirements MODIFY COLUMN applies_to {_enum(['owner', dst, 'admin'])} NOT NULL DEFAULT '{dst}'"
    )
    # notifications.type -- final order must match the model's (MySQL compares ENUMs positionally)
    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_notification_types(src, dst))} NOT NULL")
    for suffix in ("suspended", "reactivated"):
        op.execute(f"UPDATE notifications SET type = '{dst}_{suffix}' WHERE type = '{src}_{suffix}'")
    op.execute(f"ALTER TABLE notifications MODIFY COLUMN type {_enum(_notification_types(dst))} NOT NULL")


def _rewrite_strings(src: str, dst: str, src_path: str, dst_path: str) -> None:
    # Audit trail: the admin "account history" view filters on these exact values.
    op.execute(
        f"UPDATE audit_logs SET action = CONCAT('{dst}', SUBSTRING(action, {len(src) + 1})) WHERE action LIKE '{src}.%'"
    )
    op.execute(f"UPDATE audit_logs SET target_type = '{dst}_profile' WHERE target_type = '{src}_profile'")
    # In-app notification links point at frontend routes, which were renamed.
    op.execute(f"UPDATE notifications SET link = REPLACE(link, '/{src_path}/', '/{dst_path}/') WHERE link LIKE '/{src_path}/%'")
    op.execute(
        f"UPDATE notifications SET link = REPLACE(link, '/admin/{src_path}s', '/admin/{dst_path}s') "
        f"WHERE link LIKE '/admin/{src_path}s%'"
    )


def _move_local_documents(src: str, dst: str) -> None:
    from app.config import get_settings

    settings = get_settings()
    if settings.storage_backend != "local":
        return
    root = Path(settings.storage_root).resolve()
    old, new = root / src, root / dst
    if old.is_dir() and not new.exists():
        old.rename(new)


def upgrade() -> None:
    _swap_enums(OLD, NEW)
    for old, new in _TABLES:
        op.rename_table(old, new)
    for table in _ID_COLUMN_TABLES:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN {OLD}_id TO {NEW}_id")
    for table, old, new in _INDEXES:
        op.execute(f"ALTER TABLE {table} RENAME INDEX {old} TO {new}")
    _rewrite_strings(OLD, NEW, _OLD_PATH, _NEW_PATH)
    _move_local_documents(_OLD_BUCKET, _NEW_BUCKET)


def downgrade() -> None:
    _move_local_documents(_NEW_BUCKET, _OLD_BUCKET)
    _rewrite_strings(NEW, OLD, _NEW_PATH, _OLD_PATH)
    for table, old, new in reversed(_INDEXES):
        op.execute(f"ALTER TABLE {table} RENAME INDEX {new} TO {old}")
    for table in _ID_COLUMN_TABLES:
        op.execute(f"ALTER TABLE {table} RENAME COLUMN {NEW}_id TO {OLD}_id")
    for old, new in reversed(_TABLES):
        op.rename_table(new, old)
    _swap_enums(NEW, OLD)
