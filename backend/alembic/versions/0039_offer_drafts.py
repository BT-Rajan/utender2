"""offer drafts

Stage 5.2: Participate starts the provider's one offer on a requirement as a
draft -- the same offers row a submission later completes, so an offer has
one identity from start to finish:
  * offers.status / offer_revisions.status gain 'draft';
  * offers.amount is NULL while a draft (never once put forward);
  * offers.created_by / updated_by: who started it and last changed it;
  * every participation with no offer yet gets its draft.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-07

"""
import os
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

_OLD = ["submitted", "approved", "rejected", "withdrawn"]
_NEW = ["draft"] + _OLD  # the model's order (MySQL compares ENUMs positionally)


def _enum(values) -> str:
    return "ENUM(" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(f"ALTER TABLE offers MODIFY COLUMN status {_enum(_NEW)} NOT NULL")
        op.execute(f"ALTER TABLE offer_revisions MODIFY COLUMN status {_enum(_NEW)} NOT NULL")
    op.alter_column("offers", "amount", existing_type=sa.Numeric(15, 3), nullable=True)
    op.add_column("offers", sa.Column("created_by", sa.String(36), nullable=True))
    op.add_column("offers", sa.Column("updated_by", sa.String(36), nullable=True))
    op.create_foreign_key("fk_offers_created_by", "offers", "users", ["created_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_offers_updated_by", "offers", "users", ["updated_by"], ["id"], ondelete="SET NULL")

    rows = bind.execute(
        sa.text(
            "SELECT p.project_id, p.service_provider_id, p.organization_id, p.seen_material_revision, p.started_by, p.started_at"
            " FROM participations p WHERE NOT EXISTS (SELECT 1 FROM offers o WHERE o.project_id = p.project_id"
            " AND (o.service_provider_id = p.service_provider_id"
            " OR (p.organization_id IS NOT NULL AND o.organization_id = p.organization_id)))"
        )
    ).fetchall()
    for project_id, provider_id, organization_id, seen, started_by, started_at in rows:
        bind.execute(
            sa.text(
                "INSERT INTO offers (id, project_id, service_provider_id, organization_id, amount, status, is_suspended,"
                " revision, based_on_material_revision, created_by, updated_by, created_at, updated_at)"
                " VALUES (:i, :p, :s, :o, NULL, 'draft', 0, 1, :r, :u, :u, :t, :t)"
            ),
            {"i": str(uuid.uuid4()), "p": project_id, "s": provider_id, "o": organization_id, "r": seen or 0, "u": started_by, "t": started_at},
        )


def downgrade() -> None:
    # The schema before this revision has no draft offers, so going back
    # removes them. Refuse while any draft holds a provider's work (a price,
    # a method, assumptions, a completion period, accepted declarations)
    # unless the operator says that loss is intended -- a rollback must never
    # silently discard work. Submitted offers are never touched.
    bind = op.get_bind()
    with_work = bind.execute(sa.text(
        "SELECT COUNT(*) FROM offers WHERE status = 'draft' AND (amount IS NOT NULL OR message IS NOT NULL"
        " OR assumptions IS NOT NULL OR timeline_estimate IS NOT NULL OR item_prices IS NOT NULL OR declarations_accepted IS NOT NULL)"
    )).scalar() or 0
    if with_work and os.environ.get("ALLOW_DRAFT_LOSS") != "1":
        raise RuntimeError(
            f"{with_work} offer draft(s) hold providers' unsubmitted work, which this downgrade would delete. "
            "Export them first, or set ALLOW_DRAFT_LOSS=1 to proceed."
        )
    op.execute("DELETE FROM offers WHERE status = 'draft'")
    op.drop_constraint("fk_offers_updated_by", "offers", type_="foreignkey")
    op.drop_constraint("fk_offers_created_by", "offers", type_="foreignkey")
    op.drop_column("offers", "updated_by")
    op.drop_column("offers", "created_by")
    op.alter_column("offers", "amount", existing_type=sa.Numeric(15, 3), nullable=False)
    if op.get_bind().dialect.name == "mysql":
        op.execute(f"ALTER TABLE offer_revisions MODIFY COLUMN status {_enum(_OLD)} NOT NULL")
        op.execute(f"ALTER TABLE offers MODIFY COLUMN status {_enum(_OLD)} NOT NULL")
