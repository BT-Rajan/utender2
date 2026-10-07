"""feed search and eligibility columns

Stage 4.2 follow-up: derived columns the provider feed queries directly --
normalized search text (title, type of work, place, scope) and the
eligibility rules as plain columns -- kept in step on every save by
models.project.sync_derived. Backfilled here the same way.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-07

"""
import json

import sqlalchemy as sa
from alembic import op

from app.services.search_text import GOVERNORATE_NAMES, normalize

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None

_COLUMNS = [
    sa.Column("search_title", sa.String(300), nullable=True),
    sa.Column("search_trade", sa.String(150), nullable=True),
    sa.Column("search_place", sa.String(300), nullable=True),
    sa.Column("search_scope", sa.Text(), nullable=True),
    sa.Column("elig_org_only", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("elig_match_category", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("elig_match_governorate", sa.Boolean(), nullable=False, server_default="0"),
    sa.Column("elig_quals", sa.String(2000), nullable=True),
]


def upgrade() -> None:
    for column in _COLUMNS:
        op.add_column("projects", column)
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, title, trade, area, governorate, description, provider_eligibility FROM projects")).fetchall()
    for pid, title, trade, area, governorate, description, rules in rows:
        if isinstance(rules, str):
            rules = json.loads(rules)
        rules = rules or {}
        quals = sorted(set(rules.get("qualifications") or []))
        bind.execute(
            sa.text(
                "UPDATE projects SET search_title = :t, search_trade = :tr, search_place = :pl, search_scope = :sc,"
                " elig_org_only = :o, elig_match_category = :mc, elig_match_governorate = :mg, elig_quals = :q WHERE id = :i"
            ),
            {
                "t": normalize(title)[:300], "tr": normalize(trade)[:150] or None,
                "pl": normalize(" ".join(x for x in (area, GOVERNORATE_NAMES.get(governorate or "")) if x))[:300] or None,
                "sc": normalize(description) or None,
                "o": rules.get("provider_type") == "organization", "mc": bool(rules.get("match_category")),
                "mg": bool(rules.get("match_governorate")), "q": ("," + ",".join(quals) + ",") if quals else None, "i": pid,
            },
        )


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("projects", column.name)
