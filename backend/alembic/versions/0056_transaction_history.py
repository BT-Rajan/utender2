"""transaction history

Stage 7.13: the post-award business events -- in force, change proposed /
agreed / rejected / withdrawn / lapsed, terminated, completed -- are written
to the execution-history log (execution_updates, numbered per agreement) so
the transaction's history has one authoritative order. Adds
execution_updates.variation_id and backfills those events for existing
agreements from the times already recorded on them, renumbering each
agreement's log in time order.

Downgrade removes the backfilled/new event rows and the column, and
renumbers the remaining log.

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-08

"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

_EVENTS = ("in_force", "document", "change_proposed", "change_agreed", "change_rejected", "change_withdrawn", "change_lapsed", "terminated", "completed")
# Within one second, the only order these can have happened in.
_RANK = {"in_force": 0, "document": 1, "change_proposed": 1, "started": 2, "progress": 2, "on_hold": 2, "resumed": 2, "delivered": 2,
         "accepted": 2, "returned": 2, "change_agreed": 3, "change_rejected": 3, "change_withdrawn": 3,
         "change_lapsed": 4, "terminated": 5, "completed": 6}


def _renumber(bind, agreement_id):
    rows = bind.execute(sa.text(
        "SELECT id, kind, created_at, sequence FROM execution_updates WHERE agreement_id = :a"), {"a": agreement_id}).fetchall()
    ordered = sorted(rows, key=lambda r: (r.created_at, _RANK.get(r.kind, 2), r.sequence))
    for n, r in enumerate(ordered, start=1):  # two passes keep (agreement, sequence) unique throughout
        bind.execute(sa.text("UPDATE execution_updates SET sequence = :s WHERE id = :i"), {"s": 100000 + n, "i": r.id})
    for n, r in enumerate(ordered, start=1):
        bind.execute(sa.text("UPDATE execution_updates SET sequence = :s WHERE id = :i"), {"s": n, "i": r.id})


def upgrade() -> None:
    op.add_column("execution_updates", sa.Column("variation_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_execution_updates_variation", "execution_updates", "variations", ["variation_id"], ["id"], ondelete="SET NULL")
    op.add_column("execution_updates", sa.Column("document_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_execution_updates_document", "execution_updates", "agreement_documents", ["document_id"], ["id"], ondelete="SET NULL")
    bind = op.get_bind()

    def add(agreement_id, kind, party, by, note, at, variation_id=None, document_id=None):
        bind.execute(sa.text(
            "INSERT INTO execution_updates (id, agreement_id, sequence, kind, party, recorded_by, note, variation_id, document_id, created_at)"
            " VALUES (:id, :a, :s, :k, :p, :b, :n, :v, :d, :t)"),
            {"id": str(uuid.uuid4()), "a": agreement_id, "s": 200000 + add.n, "k": kind, "p": party or "owner",
             "b": by, "n": note, "v": variation_id, "d": document_id, "t": at})
        add.n += 1
    add.n = 0

    agreements = bind.execute(sa.text(
        "SELECT id, activated_at, terminated_at, termination_reason, completed_at, completion_decided_by, updated_by FROM agreements")).fetchall()
    for ag in agreements:
        if ag.activated_at:
            add(ag.id, "in_force", "owner", None, None, ag.activated_at)
        evidence = ("progress_photo", "site_report", "delivery_record", "completion_report", "inspection_report", "test_result")
        for d in bind.execute(sa.text(
                "SELECT id, kind, party, uploaded_by, file_name, uploaded_at FROM agreement_documents WHERE agreement_id = :a"
                " AND milestone_id IS NULL AND variation_id IS NULL AND execution_update_id IS NULL"), {"a": ag.id}).fetchall():
            if d.kind not in evidence:
                add(ag.id, "document", d.party, d.uploaded_by, d.file_name, d.uploaded_at, document_id=d.id)
        for v in bind.execute(sa.text(
                "SELECT id, status, description, proposed_party, proposed_by, proposed_at, decided_party, decided_by, decided_at, decision_note"
                " FROM variations WHERE agreement_id = :a"), {"a": ag.id}).fetchall():
            add(ag.id, "change_proposed", v.proposed_party, v.proposed_by, v.description, v.proposed_at, v.id)
            if v.status in ("agreed", "rejected", "withdrawn") and v.decided_at:
                add(ag.id, f"change_{v.status}", v.decided_party, v.decided_by, v.decision_note, v.decided_at, v.id)
            elif v.status == "lapsed" and ag.terminated_at:
                add(ag.id, "change_lapsed", "owner", None, None, ag.terminated_at, v.id)
        if ag.terminated_at:
            add(ag.id, "terminated", "owner", None, ag.termination_reason, ag.terminated_at)
        if ag.completed_at:
            add(ag.id, "completed", "owner", ag.completion_decided_by, None, ag.completed_at)
        _renumber(bind, ag.id)


def downgrade() -> None:
    bind = op.get_bind()
    kinds = ", ".join(f"'{k}'" for k in _EVENTS)
    bind.execute(sa.text(f"DELETE FROM execution_updates WHERE kind IN ({kinds})"))
    for (agreement_id,) in bind.execute(sa.text("SELECT DISTINCT agreement_id FROM execution_updates")).fetchall():
        _renumber(bind, agreement_id)
    op.drop_constraint("fk_execution_updates_document", "execution_updates", type_="foreignkey")
    op.drop_column("execution_updates", "document_id")
    op.drop_constraint("fk_execution_updates_variation", "execution_updates", type_="foreignkey")
    op.drop_column("execution_updates", "variation_id")
