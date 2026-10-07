"""published change integrity

Stage 3.17:
  * project_amendments.changes: each changed field's before/after, so what
    providers saw before an amendment can be reconstructed;
  * project_amendments.material_revision: the requirement version in force
    after the amendment (backfilled by counting material amendments);
  * project_drawings.material_revision: the version a file became current in
    (backfilled from the documents amendment recorded with it; 0 = as
    published);
  * offer_revisions.based_on_material_revision: the version each earlier
    submission was made against (backfilled from the offer: unknown before);
  * projects.restarted_from_id: the ended requirement a draft was started
    again from (Stage 3.16 follow-up).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-07

"""
import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_amendments", sa.Column("changes", sa.JSON(), nullable=True))
    op.add_column("project_amendments", sa.Column("material_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("project_drawings", sa.Column("material_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("offer_revisions", sa.Column("based_on_material_revision", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("projects", sa.Column("restarted_from_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_projects_restarted_from", "projects", "projects", ["restarted_from_id"], ["id"], ondelete="SET NULL")
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, project_id, material FROM project_amendments ORDER BY project_id, amendment_number")).fetchall()
    version: dict[str, int] = {}
    for amendment_id, project_id, material in rows:
        version[project_id] = version.get(project_id, 0) + (1 if material else 0)
        bind.execute(sa.text("UPDATE project_amendments SET material_revision = :v WHERE id = :i"), {"v": version[project_id], "i": amendment_id})
    # Files added after publication were recorded with a "documents" amendment
    # just after the upload: the first such amendment at or after it.
    drawings = bind.execute(sa.text(
        "SELECT d.id, d.project_id, d.uploaded_at FROM project_drawings d JOIN projects p ON p.id = d.project_id"
        " WHERE p.published_at IS NOT NULL AND d.uploaded_at >= p.published_at"
    )).fetchall()
    for drawing_id, project_id, uploaded_at in drawings:
        found = bind.execute(sa.text(
            "SELECT MIN(material_revision) FROM project_amendments WHERE project_id = :p AND material = :t"
            " AND changed_fields LIKE '%documents%' AND created_at >= :u"
        ), {"p": project_id, "t": True, "u": uploaded_at}).scalar()
        if found:
            bind.execute(sa.text("UPDATE project_drawings SET material_revision = :v WHERE id = :i"), {"v": found, "i": drawing_id})

def downgrade() -> None:
    op.drop_constraint("fk_projects_restarted_from", "projects", type_="foreignkey")
    op.drop_column("projects", "restarted_from_id")
    op.drop_column("offer_revisions", "based_on_material_revision")
    op.drop_column("project_drawings", "material_revision")
    op.drop_column("project_amendments", "material_revision")
    op.drop_column("project_amendments", "changes")
