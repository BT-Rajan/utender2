import time

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.project import ProjectDrawing
from app.services.file_security import (
    ALLOWED_DRAWING_EXTENSIONS,
    assert_allowed_extension,
    safe_relative_name,
    sanitize_path_segment,
)
from app.services.storage import Storage
from app.services.zip_utils import ZipSecurityError, extract_zip, is_zip_filename


# A revised drawing is a new row, never an overwrite (spec §2.8/§25/§67):
# uploading a file whose name matches an existing *current* drawing on this
# project supersedes it — the old row's is_current flips false and stays in
# the database and in storage untouched, the new row takes over as current
# at revision+1. Matching by file_name (case-insensitive) is what lets an
# owner "replace" a drawing through the same plain upload control used for
# adding brand new ones, with no separate "replace" UI required.
# Stage 3.6: what a requirement document is. Stored on ProjectDrawing.category.
DOCUMENT_CATEGORIES = ("drawing", "boq", "specification", "photo", "site", "other")


def _record_drawing(
    db: Session, project_id: str, file_path: str, file_name: str, category: str = "drawing", is_required: bool = True
) -> None:
    current = (
        db.query(ProjectDrawing)
        .filter(
            ProjectDrawing.project_id == project_id,
            ProjectDrawing.is_current.is_(True),
            ProjectDrawing.file_name.ilike(file_name),
        )
        .first()
    )
    next_revision = 1
    if current:
        current.is_current = False
        next_revision = current.revision + 1
    db.add(
        ProjectDrawing(
            project_id=project_id,
            file_path=file_path,
            file_name=file_name,
            revision=next_revision,
            is_current=True,
            category=category,
            is_required=is_required,
        )
    )
    # Autoflush is off on this session (see db.py) — flush explicitly so a
    # same-named file appearing twice within one batch (e.g. two zip
    # entries sharing a name) is still detected as a revision of the one
    # just added, not two independent "current" rows.
    db.flush()


# Used by both project creation and "add more drawings" on an existing
# project. A zip is transparently extracted into one project_drawings row
# per file inside it; anything else is uploaded as-is. One bad file/zip
# entry doesn't block the rest — each is best-effort.
async def upload_drawings_for_project(
    db: Session,
    storage: Storage,
    project_id: str,
    files: list[UploadFile],
    category: str = "drawing",
    is_required: bool = True,
) -> dict[str, int]:
    uploaded = 0
    failed = 0

    for file in files:
        if not file or not file.filename:
            continue
        assert_allowed_extension(file.filename, ALLOWED_DRAWING_EXTENSIONS)
        content = await file.read()
        if not content:
            continue

        if is_zip_filename(file.filename, file.content_type):
            try:
                entries = extract_zip(content)
            except ZipSecurityError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except Exception:
                failed += 1
                continue

            for entry in entries:
                name = safe_relative_name(entry.name)
                # The outer file passed the extension check, but its contents
                # didn't: skip anything that isn't a drawing type (and nested
                # archives), counted as failed like any other bad entry.
                try:
                    assert_allowed_extension(name, ALLOWED_DRAWING_EXTENSIONS - {"zip"})
                except HTTPException:
                    failed += 1
                    continue
                path = f"{project_id}/{int(time.time() * 1000)}-{sanitize_path_segment(name)}"
                try:
                    storage.save("project-drawings", path, entry.content, entry.content_type)
                except Exception:
                    failed += 1
                    continue
                _record_drawing(db, project_id, path, name, category, is_required)
                uploaded += 1
            continue

        path = f"{project_id}/{int(time.time() * 1000)}-{sanitize_path_segment(file.filename)}"
        try:
            storage.save("project-drawings", path, content, file.content_type or "application/octet-stream")
        except Exception:
            failed += 1
            continue
        _record_drawing(db, project_id, path, safe_relative_name(file.filename), category, is_required)
        uploaded += 1

    db.commit()
    return {"uploaded": uploaded, "failed": failed}
