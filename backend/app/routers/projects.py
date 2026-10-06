from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.db import get_db
from app.deps import get_current_user, require_verified_owner
from app.models.award_record import AwardRecord
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import NotificationType, OfferStatus, PricingBasis, ProjectStatus, TenderType, UserRole
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.project import Project, ProjectDrawing, ProjectItem
from app.models.project_amendment import ProjectAmendment
from app.models.user import User
from app.schemas.amendment import ProjectAmendmentOut, ProjectAmendmentRequest
from app.schemas.award import AwardRecordOut
from app.schemas.project import DrawingOut, ProjectCreate, ProjectDetailOut, ProjectItemOut, ProjectItemsUpdate
from app.services.drawings import upload_drawings_for_project
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS, assert_allowed_extension, safe_relative_name
from app.services.email import notify_service_provider_tender_amended
from app.services.notify import notify
from app.services.storage import drawing_url_expiry_seconds, get_storage
from app.services.tender_lifecycle import lock_project, sync_expired_projects

router = APIRouter(prefix="/projects", tags=["projects"])


# Full project detail includes signed drawing URLs — the P0 payment gate
# (spec checklist "docs approved but payment absent") applies here, not
# just verification. A verification-approved-but-unpaid service provider sees a
# 404 on this endpoint exactly like a project they're not eligible for at
# all — the response never distinguishes "doesn't exist" from "you don't
# have access yet", so it can't be used to enumerate projects. The
# lightweight /service-provider/feed listing (title, deadline, offer count — no
# drawings) stays available on verification alone; that split is what lets
# an unpaid service provider browse before paying instead of a hard app lockout.
def _can_view_project(user: User, project: Project, db: Session) -> bool:
    if user.role == UserRole.admin or project.owner_id == user.id:
        return True
    if user.role != UserRole.service_provider:
        return False
    # Draft is the only status a service provider never sees — every other state,
    # including the newer under_evaluation/no_award/canceled/expired, stays
    # visible so a service provider who bid can still see what happened to their
    # bid after bidding itself has ended. An admin-suspended project is
    # blocked the same way, even for a service provider who already bid on it —
    # suspension is a moderation action meant to pull the whole project out
    # of sight until an admin reactivates it.
    if project.status == ProjectStatus.draft or project.is_suspended:
        return False
    profile = db.get(ServiceProviderProfile, user.id)
    return bool(profile and profile.is_verified_active)


# The scope of work lives in Project.description (a TEXT column: 64 KB). A
# clear limit, well inside that even for multi-byte Arabic text, so an
# over-long scope is a 400 the owner can act on rather than a database error.
MAX_SCOPE_CHARS = 20_000


def _check_scope_length(text: str | None) -> None:
    if text and len(text) > MAX_SCOPE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"The scope of work is too long ({len(text):,} characters; the limit is {MAX_SCOPE_CHARS:,}).",
        )


def _parse_bid_deadline(raw: str) -> datetime:
    """Parses an ISO 8601 deadline into the naive-UTC datetime this app stores
    everywhere (see `datetime.utcnow()` throughout). A value carrying an
    explicit offset ("...Z", "...+03:00") is converted to UTC; a value with no
    offset is taken as UTC already, exactly as before. Anything unparseable is
    a client error, not a server error."""
    try:
        parsed = datetime.fromisoformat(raw.strip())
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, OverflowError):
        raise HTTPException(
            status_code=400,
            detail="Invalid bid deadline. Use an ISO 8601 date and time, e.g. 2030-01-31T17:00:00Z.",
        )
    return parsed


@router.post("", response_model=ProjectDetailOut, status_code=201)
async def create_project(
    title: str = Form(...),
    address: str = Form(...),
    description: str | None = Form(None),
    trade: str | None = Form(None),
    bid_deadline: str = Form(...),
    tender_type: str = Form("owner_visible"),
    # Starting a requirement creates a draft unless the owner explicitly asks
    # to publish; a client that omits status must never publish by accident.
    status: str = Form(ProjectStatus.draft.value),
    drawings: list[UploadFile] = File(default=[]),
    user: User = Depends(require_verified_owner),
    db: Session = Depends(get_db),
):
    try:
        tender_type_value = TenderType(tender_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tender type.")

    # Only these two lifecycle states can be chosen at creation — every
    # other one is reached later through an explicit owner action.
    if status not in (ProjectStatus.draft.value, ProjectStatus.open.value):
        raise HTTPException(status_code=400, detail="A new project must start as draft or open.")
    status_value = ProjectStatus(status)

    _check_scope_length(description)
    deadline = _parse_bid_deadline(bid_deadline)
    if status_value == ProjectStatus.open and deadline <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Bid deadline must be in the future.")

    # Reject disallowed drawing types before anything is created.
    for f in drawings:
        if f.filename:
            assert_allowed_extension(f.filename, ALLOWED_DRAWING_EXTENSIONS)

    project = Project(
        owner_id=user.id,
        title=title,
        address=address,
        description=description or None,
        trade=trade or None,
        bid_deadline=deadline,
        tender_type=tender_type_value,
        status=status_value,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    real_files = [f for f in drawings if f.filename]
    if real_files:
        try:
            await upload_drawings_for_project(db, get_storage(), project.id, real_files)
        except Exception:
            # A rejected file (wrong type, unsafe archive) fails the whole start:
            # remove the project and anything already stored for it, so the
            # owner is never left with a half-created requirement -- possibly
            # already published -- that a retry would then duplicate.
            _discard_project(db, project.id)
            raise
        db.refresh(project)

    return _serialize_detail(project, db)


def _discard_project(db: Session, project_id: str) -> None:
    db.rollback()
    project = db.get(Project, project_id)
    if not project:
        return
    paths = [d.file_path for d in project.drawings]
    db.delete(project)
    db.commit()
    if paths:
        try:
            get_storage().delete("project-drawings", paths)
        except Exception:
            pass  # unreferenced files are harmless; the record is what matters


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sync_expired_projects(db)
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")
    return _serialize_detail(project, db)


# A published, material change to a tender (spec §2.8/§2.12, D-007) — a
# permanent numbered record, never a silent edit. changed_fields only
# lists what actually differs from before, so a no-op PATCH (same values
# resubmitted) creates no amendment row and bumps nothing.
def _require_active_owner(user: User, db: Session) -> None:
    """A suspended (or unapproved) owner can still see their tender but can't
    change it. Same rule and same "not_approved" code as
    deps.require_verified_owner, applied *after* the ownership lookup so
    everyone else keeps getting the 404 they always did."""
    profile = db.get(OwnerProfile, user.id)
    if not profile or not profile.is_verified_active:
        raise HTTPException(status_code=403, detail="not_approved")


@router.patch("/{project_id}", response_model=ProjectDetailOut)
def amend_project(
    project_id: str, payload: ProjectAmendmentRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    sync_expired_projects(db)
    # Locked: "can't move the deadline earlier once bids exist" reads
    # tender_type_locked, which the first bid sets under this same lock.
    project = lock_project(db, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    if project.status not in (ProjectStatus.draft, ProjectStatus.open, ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise HTTPException(status_code=400, detail="This project can no longer be amended.")

    changed: list[str] = []

    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        if title != project.title:
            changed.append("title")
            project.title = title

    if payload.address is not None:
        address = payload.address.strip()
        if not address:
            raise HTTPException(status_code=400, detail="Location cannot be empty.")
        if address != project.address:
            changed.append("address")
            project.address = address

    _check_scope_length(payload.description)
    if payload.description is not None and payload.description != project.description:
        changed.append("description")
        project.description = payload.description or None

    if payload.trade is not None and payload.trade != project.trade:
        changed.append("trade")
        project.trade = payload.trade or None

    deadline_extended = False
    new_deadline = payload.bid_deadline
    if new_deadline is not None and new_deadline.tzinfo is not None:
        # Deadlines are stored as naive UTC (compared with utcnow() everywhere);
        # an explicit offset ("...Z", "...+03:00") is converted, not compared
        # raw (naive vs aware raised TypeError -> 500).
        try:
            new_deadline = new_deadline.astimezone(timezone.utc).replace(tzinfo=None)
        except OverflowError:
            raise HTTPException(status_code=400, detail="Invalid bid deadline.")
    if new_deadline is not None and new_deadline != project.bid_deadline:
        # A bid already locks the tender type (spec D-001) for the same
        # reason a deadline can't then be pulled earlier out from under
        # bidders who priced against the original window.
        if new_deadline < project.bid_deadline and project.tender_type_locked:
            raise HTTPException(status_code=400, detail="Cannot move the deadline earlier once bids have been submitted.")
        deadline_extended = new_deadline > project.bid_deadline
        changed.append("bid_deadline")
        project.bid_deadline = new_deadline

    if not changed:
        raise HTTPException(status_code=400, detail="No changes were provided.")

    # A draft is still being written: nobody has seen it, so saving it is not
    # an amendment -- no numbered record, no revision bump, no notifications.
    if project.status == ProjectStatus.draft:
        db.commit()
        db.refresh(project)
        return _serialize_detail(project, db)

    amendment_number = (
        db.query(ProjectAmendment).filter(ProjectAmendment.project_id == project_id).count() + 1
    )
    summary = f"Updated {', '.join(changed)}."
    db.add(
        ProjectAmendment(
            project_id=project_id,
            amendment_number=amendment_number,
            summary=summary,
            changed_fields=", ".join(changed),
            reason=(payload.reason or "").strip() or None,
            deadline_extended=deadline_extended,
            created_by=user.id,
        )
    )
    project.revision += 1
    db.commit()
    db.refresh(project)

    # Best-effort — every service provider with a live (non-withdrawn) bid gets
    # notified; a failed send never rolls back the amendment itself.
    bidder_ids = (
        db.query(Offer.service_provider_id)
        .filter(Offer.project_id == project_id, Offer.status != OfferStatus.withdrawn)
        .distinct()
        .all()
    )
    for (service_provider_id,) in bidder_ids:
        service_provider_user = db.get(User, service_provider_id)
        if service_provider_user:
            notify_service_provider_tender_amended(service_provider_user.email, project.title, project_id, summary)
            notify(
                db,
                service_provider_user,
                NotificationType.tender_amendment,
                link=f"/service-provider/projects/{project_id}/offer",
                project_title=project.title,
                summary=summary,
            )

    return _serialize_detail(project, db)


@router.put("/{project_id}/items", response_model=ProjectDetailOut)
def set_project_items(
    project_id: str, payload: ProjectItemsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Stage 3.4: the requirement's pricing basis and its measurable items,
    saved together and replaced as a whole. Items are optional -- a
    requirement priced as one total needs none -- but pricing per item needs
    at least one item to price."""
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    if project.status != ProjectStatus.draft:
        raise HTTPException(status_code=409, detail="Items and the pricing basis can only be changed while the requirement is a draft.")

    items = []
    for n, item in enumerate(payload.items, start=1):
        description = item.description.strip()
        if not description:
            raise HTTPException(status_code=400, detail=f"Item {n} needs a description.")
        items.append(
            ProjectItem(
                position=n,
                description=description,
                quantity=item.quantity,
                unit=(item.unit or "").strip() or None,
                specification=(item.specification or "").strip() or None,
            )
        )
    if payload.pricing_basis == PricingBasis.per_item and not items:
        raise HTTPException(status_code=400, detail="Add at least one item to price per item, or ask for one total price.")

    project.pricing_basis = payload.pricing_basis
    project.items = items  # delete-orphan removes the previous list
    db.commit()
    db.refresh(project)
    return _serialize_detail(project, db)


@router.get("/{project_id}/amendments", response_model=list[ProjectAmendmentOut])
def list_amendments(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")
    return (
        db.query(ProjectAmendment)
        .filter(ProjectAmendment.project_id == project_id)
        .order_by(ProjectAmendment.amendment_number.asc())
        .all()
    )


@router.get("/{project_id}/award", response_model=AwardRecordOut)
def get_award(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")

    record = db.query(AwardRecord).filter(AwardRecord.project_id == project_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="This project has not been awarded.")

    cp = db.get(ServiceProviderProfile, record.service_provider_id)
    return AwardRecordOut(
        id=record.id,
        project_id=record.project_id,
        offer_id=record.offer_id,
        service_provider_id=record.service_provider_id,
        amount=record.amount,
        project_revision=record.project_revision,
        offer_revision=record.offer_revision,
        awarded_by=record.awarded_by,
        created_at=record.created_at,
        service_provider_company_name=cp.company_name if cp else None,
    )


@router.post("/{project_id}/drawings", response_model=ProjectDetailOut)
async def add_drawings(
    project_id: str,
    drawings: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)

    real_files = [f for f in drawings if f.filename]
    await upload_drawings_for_project(db, get_storage(), project_id, real_files)
    db.refresh(project)
    return _serialize_detail(project, db)


@router.get("/{project_id}/drawings-zip")
def download_drawings_zip(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    import io
    import zipfile

    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")

    # Only the current revision of each drawing — a superseded version
    # stays downloadable individually via its own signed URL in the
    # history endpoint, but "download everything" means the latest set.
    drawings = (
        db.query(ProjectDrawing)
        .filter(ProjectDrawing.project_id == project_id, ProjectDrawing.is_current.is_(True))
        .all()
    )
    if not drawings:
        raise HTTPException(status_code=404, detail="No drawings on this project.")

    storage = get_storage()
    buffer = io.BytesIO()
    included = 0
    with zipfile.ZipFile(buffer, "w") as zf:
        for d in drawings:
            content = storage.download("project-drawings", d.file_path)
            if content is None:
                continue
            # Normalised here too: rows stored before names were sanitised on
            # upload may still hold a hostile path.
            zf.writestr(safe_relative_name(d.file_name), content)
            included += 1

    if included == 0:
        raise HTTPException(status_code=404, detail="No accessible drawings.")

    buffer.seek(0)
    safe_title = "".join(c for c in project.title if c.isalnum() or c in " _-").strip().replace(" ", "-") or "drawings"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}-drawings.zip"'},
    )


@router.get("/{project_id}/drawings/history", response_model=list[DrawingOut])
def drawing_history(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Every revision of every drawing on this project, superseded ones
    included — the append-only record spec §2.8/§67 require. Same
    visibility rule as the project itself; a superseded row's signed URL
    still works, so old drawings are never truly gone, just no longer the
    default one shown."""
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")

    storage = get_storage()
    expiry = drawing_url_expiry_seconds(project.bid_deadline)
    rows = (
        db.query(ProjectDrawing)
        .filter(ProjectDrawing.project_id == project_id)
        .order_by(ProjectDrawing.file_name.asc(), ProjectDrawing.revision.asc())
        .all()
    )
    return [
        DrawingOut(
            id=d.id,
            file_name=d.file_name,
            uploaded_at=d.uploaded_at,
            revision=d.revision,
            is_current=d.is_current,
            url=storage.signed_url("project-drawings", d.file_path, expiry),
        )
        for d in rows
    ]


def _serialize_detail(project: Project, db: Session) -> ProjectDetailOut:
    offer_count = db.query(Offer).filter(Offer.project_id == project.id).count()
    storage = get_storage()
    expiry = drawing_url_expiry_seconds(project.bid_deadline)
    # Current revisions only — superseded ones are never lost, just not
    # part of the default view (see /drawings/history for the full trail).
    drawing_rows = (
        db.query(ProjectDrawing)
        .filter(ProjectDrawing.project_id == project.id, ProjectDrawing.is_current.is_(True))
        .all()
    )
    drawings = [
        DrawingOut(
            id=d.id,
            file_name=d.file_name,
            uploaded_at=d.uploaded_at,
            revision=d.revision,
            is_current=d.is_current,
            url=storage.signed_url("project-drawings", d.file_path, expiry),
        )
        for d in drawing_rows
    ]
    return ProjectDetailOut(
        id=project.id,
        owner_id=project.owner_id,
        title=project.title,
        address=project.address,
        description=project.description,
        trade=project.trade,
        bid_deadline=project.bid_deadline,
        status=project.status,
        tender_type=project.tender_type,
        tender_type_locked=project.tender_type_locked,
        is_suspended=project.is_suspended,
        created_at=project.created_at,
        offer_count=offer_count,
        drawings=drawings,
        pricing_basis=project.pricing_basis,
        items=[ProjectItemOut.model_validate(i) for i in project.items],
    )
