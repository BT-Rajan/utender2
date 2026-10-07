from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from app.db import get_db
from app.deps import get_current_user, require_approved_service_provider, require_service_provider, require_verified_owner
from app.models.award_record import AwardRecord
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import NotificationType, OfferStatus, PricingBasis, ProjectStatus, TenderType, UserRole
from app.models.offer import Offer
from app.models.owner import OwnerProfile
from app.models.clarification import Clarification
from app.models.participation import Participation as ParticipationRecord
from app.models.project import Project, ProjectDrawing, ProjectItem
from app.models.project_amendment import ProjectAmendment
from app.models.user import User
from app.schemas.amendment import ProjectAmendmentOut, ProjectAmendmentRequest
from app.schemas.award import AwardRecordOut
from app.config import get_settings
from app.schemas.project import (
    Participation as ParticipationOut,
    ProviderEligibilityOut,
    OpportunityListing,
    RequirementVersionOut,
    DrawingOut,
    EligibilityCheckOut,
    ProjectCreate,
    ProjectDetailOut,
    ProjectItemOut,
    ProjectItemsUpdate,
    ProviderEligibilityIn,
    ResponseRequirements,
    CommercialConditions,
    TenderRulesIn,
    TenderRulesOut,
)
from app.services.tender_rules import questions_close_at, questions_open
from app.services.categories import resolve_trade
from app.services.eligibility import audience, ineligibility_reasons, participation, rules_for, rules_out, validate_rules
from app.services.drawings import DOCUMENT_CATEGORIES, upload_drawings_for_project
from app.services.locations import clean_area, clean_governorate
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS, assert_allowed_extension, safe_relative_name
from app.services.email import notify_service_provider_tender_amended
from app.services.notify import notify, notify_team
from app.services.team import acting_id, acting_profile, mine, org_of, owns
from app.services import requirement_quality
from app.services.storage import drawing_url_expiry_seconds, get_storage
from app.services.tender_lifecycle import interested_providers, lock_project, publish, sync_expired_projects

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
    if user.role == UserRole.admin or owns(db, user, project):
        return True
    if user.role != UserRole.service_provider:
        return False
    # A draft is never seen by providers; nor is an admin-suspended project,
    # even by a provider who already bid on it -- suspension is a moderation
    # action meant to pull the whole project out of sight until an admin
    # reactivates it.
    if project.status == ProjectStatus.draft or project.is_suspended:
        return False
    profile = acting_profile(db, user)
    if not (profile and profile.is_verified_active):
        return False
    has_bid = (
        db.query(Offer.id).filter(Offer.project_id == project.id, mine(db, user, Offer, Offer.service_provider_id)).first() is not None
    )
    # Once offers have closed (closed, under evaluation, awarded, no award,
    # canceled, expired -- including a draft that expired unpublished), only
    # providers who took part can still open it, to see what happened to
    # their bid. Nobody else needs the exact address and scope any more.
    if project.status != ProjectStatus.open:
        return has_bid
    # Stage 3.9: open, and eligible for this particular requirement -- or
    # already bidding on it (so a lapsed qualification never hides a
    # provider's own bid; it only stops new or revised offers).
    return has_bid or not ineligibility_reasons(db, project, profile)


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


MAX_DURATION_DAYS = 3650


def _check_execution_timing(deadline: datetime, start: date | None, completion: date | None, duration: int | None) -> None:
    """Stage 3.7: reject expected work timing that contradicts itself or the
    response deadline. Work can't be expected to start (or finish) before
    providers have even finished responding."""
    if completion and duration:
        raise HTTPException(status_code=400, detail="Give either an expected completion date or a duration, not both.")
    if duration is not None and not 1 <= duration <= MAX_DURATION_DAYS:
        raise HTTPException(status_code=400, detail=f"Duration must be between 1 and {MAX_DURATION_DAYS} days.")
    if start and completion and completion < start:
        raise HTTPException(status_code=400, detail="The expected completion date can't be before the expected start date.")
    response_closes = deadline.date()
    if start and start < response_closes:
        raise HTTPException(status_code=400, detail="Work can't be expected to start before the response deadline.")
    if completion and completion < response_closes:
        raise HTTPException(status_code=400, detail="Work can't be expected to finish before the response deadline.")


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
    governorate: str | None = Form(None),
    area: str | None = Form(None),
    description: str | None = Form(None),
    trade: str | None = Form(None),
    category_id: str | None = Form(None),
    creation_token: str | None = Form(None, max_length=64),
    bid_deadline: str = Form(...),
    expected_start_date: date | None = Form(None),
    expected_completion_date: date | None = Form(None),
    expected_duration_days: int | None = Form(None),
    tender_type: str = Form("owner_visible"),
    # Starting a requirement creates a draft unless the owner explicitly asks
    # to publish; a client that omits status must never publish by accident.
    status: str = Form(ProjectStatus.draft.value),
    drawings: list[UploadFile] = File(default=[]),
    user: User = Depends(require_verified_owner),
    db: Session = Depends(get_db),
):
    # Stage 3.11: the same start sent again (double click, retry after a lost
    # response) returns the draft it already created.
    if creation_token:
        existing = db.query(Project).filter(Project.owner_id == acting_id(db, user), Project.creation_token == creation_token).first()
        if existing:
            return _serialize_detail(existing, db)
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
    category_value, trade = resolve_trade(db, category_id, trade)
    governorate_value, area_value = clean_governorate(governorate), clean_area(area)
    deadline = _parse_bid_deadline(bid_deadline)
    # A draft is prepared for a future deadline too: a draft whose deadline
    # passes expires (Stage 3.11).
    if deadline <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="Bid deadline must be in the future.")
    _check_execution_timing(deadline, expected_start_date, expected_completion_date, expected_duration_days)

    # Reject disallowed drawing types before anything is created.
    for f in drawings:
        if f.filename:
            assert_allowed_extension(f.filename, ALLOWED_DRAWING_EXTENSIONS)

    project = Project(
        # Recorded under the stakeholder this person acts as (their
        # organization's profile, for a member: services.team).
        owner_id=acting_id(db, user),
        title=title,
        address=address,
        governorate=governorate_value,
        area=area_value,
        description=description or None,
        trade=trade,
        category_id=category_value,
        bid_deadline=deadline,
        expected_start_date=expected_start_date,
        expected_completion_date=expected_completion_date,
        expected_duration_days=expected_duration_days,
        tender_type=tender_type_value,
        # Always created as a draft; "publish now" publishes it below, through
        # the one publication transition, once its files are in place.
        status=ProjectStatus.draft,
        creation_token=creation_token or None,
        organization_id=org_of(db, user.id),  # an organization's requirement is shared by its members
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        # Two copies of the same start arrived at once: the other one won.
        db.rollback()
        existing = db.query(Project).filter(Project.owner_id == acting_id(db, user), Project.creation_token == creation_token).first()
        if not existing:
            raise
        return _serialize_detail(existing, db)
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

    if status_value == ProjectStatus.open:
        # Stage 3.14: "publish now" from the start form is the same transition
        # as the Publish button (quality gate, deadline, timestamp, audit). If
        # it is refused, nothing is left behind: not a draft the owner didn't
        # ask for, and never a half-published requirement.
        try:
            publish(db, lock_project(db, project.id), user.id)
        except HTTPException:
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
    detail = _serialize_detail(project, db)
    if owns(db, user, project):
        detail.closure_note = project.closure_note  # Stage 3.16: the owner's private note, never a provider's to see
        detail.restarted_from_id = project.restarted_from_id
    elif user.role == UserRole.service_provider:
        # Stage 4.4: whether this provider may respond, and if not why -- the
        # same check the offer endpoints enforce. (Only ever their own.)
        profile = acting_profile(db, user)
        reasons = ineligibility_reasons(db, project, profile)
        detail.eligible, detail.ineligible_reasons = not reasons, reasons
        detail.participation = participation(db, project, profile, reasons)  # Stage 4.5
        _with_decision(db, user, project, detail.participation)  # Stage 4.9
        from app.models.saved_opportunity import SavedOpportunity

        detail.saved = db.query(SavedOpportunity.id).filter(  # Stage 4.8
            SavedOpportunity.project_id == project.id, mine(db, user, SavedOpportunity, SavedOpportunity.service_provider_id)
        ).first() is not None
    return detail


# A published, material change to a tender (spec §2.8/§2.12, D-007) — a
# permanent numbered record, never a silent edit. changed_fields only
# lists what actually differs from before, so a no-op PATCH (same values
# resubmitted) creates no amendment row and bumps nothing.
def _require_active_owner(user: User, db: Session) -> None:
    """A suspended (or unapproved) owner can still see their tender but can't
    change it. Same rule and same "not_approved" code as
    deps.require_verified_owner, applied *after* the ownership lookup so
    everyone else keeps getting the 404 they always did."""
    profile = acting_profile(db, user)
    if not profile or not profile.is_verified_active:
        raise HTTPException(status_code=403, detail="not_approved")


def _guard_draft_write(project: Project, if_match: str | None) -> None:
    """Stage 3.11: a discarded or expired draft is closed to changes; and a
    save sent from a page showing an older version (another tab, another
    device, another member of the organization) is refused rather than
    silently overwriting newer work. Callers hold the row lock
    (lock_project), so the check and the version bump are one step: two
    saves can never both pass against the same version. If-Match carries
    the version the page last saw."""
    if project.discarded_at is not None:
        raise HTTPException(status_code=409, detail="This draft was discarded and can no longer be changed.")
    if if_match and if_match.strip('"') != str(project.version):
        raise HTTPException(
            status_code=409,
            detail="This requirement was changed somewhere else (another tab, device or team member) since you opened it. Reload to see the latest version, then make your change again.",
        )
    _touch(project)


def _touch(project: Project) -> None:
    project.version = (project.version or 0) + 1
    project.updated_at = datetime.utcnow().replace(microsecond=0)


# Stage 3.15: what a published amendment means for providers. Material =
# changes what they price (what the work is, where, when it happens, the
# documents); a title correction or more time is not. A material change moves
# the requirement's material_revision on, so offers made against the earlier
# one are flagged for their providers to review and confirm or revise -- never
# silently left priced against something that no longer exists -- and it must
# leave providers time to do that.
MATERIAL_FIELDS = {
    "description", "trade", "address", "governorate", "area",
    "expected_start_date", "expected_completion_date", "expected_duration_days", "documents",
}
MATERIAL_NOTICE = timedelta(days=3)


# Stage 3.17: the fields an amendment can change, whose before/after is kept
# so the requirement as providers saw it at any version can be rebuilt.
TRACKED_FIELDS = (
    "title", "address", "governorate", "area", "description", "documents_required", "trade", "category_id",
    "bid_deadline", "expected_start_date", "expected_completion_date", "expected_duration_days",
)


def _plain(value):
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat() + "Z"
    if isinstance(value, date):
        return value.isoformat()
    return value


def _field_changes(before: dict, project: Project) -> dict:
    return {f: {"from": _plain(before[f]), "to": _plain(getattr(project, f))} for f in TRACKED_FIELDS if before[f] != getattr(project, f)}


def _record_amendment(
    db: Session, project: Project, user: User, changed: list[str], reason: str | None, deadline_extended: bool = False,
    changes: dict | None = None, documents: list[ProjectDrawing] = (),
) -> None:
    material = bool(MATERIAL_FIELDS & set(changed))
    if material and project.bid_deadline - datetime.utcnow() < MATERIAL_NOTICE:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="A change to what providers price needs at least 3 days before offers close. Extend the deadline in the same change.",
        )
    amendment_number = db.query(ProjectAmendment).filter(ProjectAmendment.project_id == project.id).count() + 1
    summary = f"Updated {', '.join(changed)}."
    project.revision += 1
    if material:
        project.material_revision += 1
    amendment = ProjectAmendment(
        project_id=project.id,
        amendment_number=amendment_number,
        summary=summary,
        changed_fields=", ".join(changed),
        reason=reason,
        deadline_extended=deadline_extended,
        material=material,
        changes=changes or {},
        material_revision=project.material_revision,
        created_by=user.id,
    )
    db.add(amendment)
    db.flush()
    for document in documents:  # files this amendment brought in belong to its version
        document.amendment_id = amendment.id
        document.material_revision = project.material_revision
    db.commit()
    db.refresh(project)

    # Best-effort — every service provider with a live (non-withdrawn) bid gets
    # notified; a failed send never rolls back the amendment itself.
    if material:
        summary += " Review your offer: confirm it still stands, or revise it."
    bidder_ids = (
        db.query(Offer.service_provider_id, Offer.organization_id)
        .filter(Offer.project_id == project.id, Offer.status != OfferStatus.withdrawn)
        .distinct()
        .all()
    )
    for service_provider_id, organization_id in bidder_ids:
        service_provider_user = db.get(User, service_provider_id)
        if service_provider_user:
            notify_service_provider_tender_amended(service_provider_user.email, project.title, project.id, summary)
            notify_team(
                db,
                service_provider_user,
                NotificationType.tender_amendment,
                link=f"/service-provider/projects/{project.id}/offer",
                organization_id=organization_id,
                project_title=project.title,
                summary=summary,
            )
    # Stage 3.17: a change to what is priced also reaches the providers who
    # were told about it or asked about it but haven't offered yet -- they may
    # be preparing one against the earlier version.
    if material:
        for person in interested_providers(db, project):
            notify(
                db, person, NotificationType.tender_amendment, link=f"/service-provider/projects/{project.id}/offer",
                project_title=project.title, summary=f"Updated {', '.join(changed)}. Check the current version before you prepare an offer.",
            )
        db.commit()


@router.patch("/{project_id}", response_model=ProjectDetailOut)
def amend_project(
    project_id: str,
    payload: ProjectAmendmentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    if_match: str | None = Header(None, alias="If-Match"),
):
    sync_expired_projects(db)
    # Locked: "can't move the deadline earlier once bids exist" reads
    # tender_type_locked, which the first bid sets under this same lock.
    project = lock_project(db, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    _guard_draft_write(project, if_match)
    # Stage 3.15: once offers have closed, the requirement they were made
    # against is the record the owner evaluates -- it is no longer changed.
    if project.status not in (ProjectStatus.draft, ProjectStatus.open):
        raise HTTPException(status_code=400, detail="This project can no longer be amended.")

    # Stage 4.7: a change made because of an answered question is tied to it.
    clarification = None
    if payload.clarification_id:
        clarification = db.get(Clarification, payload.clarification_id)
        if not clarification or clarification.project_id != project.id or clarification.answer is None:
            raise HTTPException(status_code=400, detail="Choose an answered question on this requirement.")
        if project.status == ProjectStatus.draft:
            raise HTTPException(status_code=400, detail="Choose an answered question on this requirement.")

    before = {f: getattr(project, f) for f in TRACKED_FIELDS}
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

    # Stage 3.9: once published, providers were told who may respond on the
    # basis of the category and governorate; a rule that depends on one fixes it.
    rules = rules_for(project)
    published = project.status != ProjectStatus.draft

    if "governorate" in payload.model_fields_set:
        governorate = clean_governorate(payload.governorate)
        if governorate != project.governorate:
            if published and rules.match_governorate:
                raise HTTPException(status_code=409, detail="Who can respond depends on the governorate, so it can't be changed after publishing.")
            changed.append("governorate")
            project.governorate = governorate

    if "area" in payload.model_fields_set:
        area = clean_area(payload.area)
        if area != project.area:
            changed.append("area")
            project.area = area

    _check_scope_length(payload.description)
    if payload.description is not None and payload.description != project.description:
        changed.append("description")
        project.description = payload.description or None

    if payload.documents_required is not None and payload.documents_required != project.documents_required:
        changed.append("documents_required")
        project.documents_required = payload.documents_required

    if "category_id" in payload.model_fields_set or payload.trade is not None:
        category_value, trade = resolve_trade(db, payload.category_id, payload.trade)
        if (category_value, trade) != (project.category_id, project.trade):
            if published and rules.match_category and category_value != project.category_id:
                raise HTTPException(status_code=409, detail="Who can respond depends on the type of work, so it can't be changed after publishing.")
            changed.append("trade")
            project.category_id, project.trade = category_value, trade

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
        if new_deadline <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="The offer deadline must be in the future.")
        # Stage 3.10: questions close before offers do.
        if project.questions_deadline and new_deadline <= project.questions_deadline:
            raise HTTPException(status_code=400, detail="The offer deadline must be after the question deadline.")
        deadline_extended = new_deadline > project.bid_deadline
        changed.append("bid_deadline")
        project.bid_deadline = new_deadline

    for field in ("expected_start_date", "expected_completion_date", "expected_duration_days"):
        if field in payload.model_fields_set and getattr(payload, field) != getattr(project, field):
            changed.append(field)
            setattr(project, field, getattr(payload, field))
    if changed:
        _check_execution_timing(
            project.bid_deadline, project.expected_start_date, project.expected_completion_date, project.expected_duration_days
        )

    if not changed:
        raise HTTPException(status_code=400, detail="No changes were provided.")

    # A draft is still being written: nobody has seen it, so saving it is not
    # an amendment -- no numbered record, no revision bump, no notifications.
    if project.status == ProjectStatus.draft:
        db.commit()
        db.refresh(project)
        return _serialize_detail(project, db)

    reason = (payload.reason or "").strip() or None
    if clarification is not None and not reason:
        reason = f"Following a question: {clarification.question[:200]}"
    _record_amendment(db, project, user, changed, reason, deadline_extended, _field_changes(before, project))
    if clarification is not None:
        latest = db.query(ProjectAmendment).filter(ProjectAmendment.project_id == project.id).order_by(ProjectAmendment.amendment_number.desc()).first()
        clarification.amendment_id = latest.id
        db.commit()
    return _serialize_detail(project, db)


@router.put("/{project_id}/items", response_model=ProjectDetailOut)
def set_project_items(
    project_id: str, payload: ProjectItemsUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db),
    if_match: str | None = Header(None, alias="If-Match"),
):
    """Stage 3.4: the requirement's pricing basis and its measurable items,
    saved together and replaced as a whole. Items are optional -- a
    requirement priced as one total needs none -- but pricing per item needs
    at least one item to price."""
    project = lock_project(db, project_id)  # saves are serialized; the version check runs under the lock
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    _guard_draft_write(project, if_match)
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


@router.put("/{project_id}/response-requirements", response_model=ProjectDetailOut)
def set_response_requirements(
    project_id: str, payload: ResponseRequirements, user: User = Depends(get_current_user), db: Session = Depends(get_db),
    if_match: str | None = Header(None, alias="If-Match"),
):
    """Stage 3.8: what providers must submit with their price. Owner only,
    while a draft -- once published, providers rely on these terms."""
    project = lock_project(db, project_id)  # saves are serialized; the version check runs under the lock
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    _guard_draft_write(project, if_match)
    if project.status != ProjectStatus.draft:
        raise HTTPException(status_code=409, detail="Response requirements can only be changed while the requirement is a draft.")
    project.response_requirements = payload.model_dump()
    db.commit()
    db.refresh(project)
    return _serialize_detail(project, db)


def _to_naive_utc(value: datetime | None, label: str) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    try:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    except OverflowError:
        raise HTTPException(status_code=400, detail=f"Invalid {label}.")


@router.get("/{project_id}/audience")
def requirement_audience(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stage 3.13: how many verified providers this requirement's eligibility
    rules would reach (counts only). The owner's side only."""
    project = db.get(Project, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    return audience(db, project)


@router.get("/{project_id}/quality")
def requirement_quality_report(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stage 3.12: what is still missing or contradictory before this
    requirement can go in front of providers (errors block publication;
    warnings are advice). The owner's side only."""
    sync_expired_projects(db)
    project = db.get(Project, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    return requirement_quality.check(db, project).as_dict()


@router.put("/{project_id}/tender-rules", response_model=ProjectDetailOut)
def set_tender_rules(
    project_id: str,
    payload: TenderRulesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    if_match: str | None = Header(None, alias="If-Match"),
):
    """Stage 3.10: how the opportunity is run -- who sees offers when,
    whether and until when questions are taken, and the owner's commercial
    conditions and instructions. Owner only, while a draft."""
    project = lock_project(db, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    _guard_draft_write(project, if_match)
    if project.status != ProjectStatus.draft:
        raise HTTPException(status_code=409, detail="Tender rules can only be changed while the requirement is a draft.")
    if payload.tender_type != project.tender_type and project.tender_type_locked:
        raise HTTPException(status_code=409, detail="Offer visibility can't change once an offer exists.")

    cutoff = _to_naive_utc(payload.questions_deadline, "question deadline") if payload.questions_allowed else None
    if cutoff is not None:
        if cutoff <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="The question deadline must be in the future.")
        if cutoff >= project.bid_deadline:
            raise HTTPException(status_code=400, detail="Questions must close before offers close.")
    for text in (payload.commercial_terms, payload.bidder_instructions):
        _check_scope_length(text)

    project.tender_type = payload.tender_type
    project.questions_allowed = payload.questions_allowed
    project.questions_deadline = cutoff
    project.commercial_conditions = payload.commercial_conditions.model_dump(mode="json")
    project.commercial_terms = (payload.commercial_terms or "").strip() or None
    project.bidder_instructions = (payload.bidder_instructions or "").strip() or None
    db.commit()
    db.refresh(project)
    return _serialize_detail(project, db)


@router.put("/{project_id}/eligibility", response_model=ProjectDetailOut)
def set_provider_eligibility(
    project_id: str, payload: ProviderEligibilityIn, user: User = Depends(get_current_user), db: Session = Depends(get_db),
    if_match: str | None = Header(None, alias="If-Match"),
):
    """Stage 3.9: who may respond. Owner only, while a draft -- once
    published, providers have decided whether to respond on these terms."""
    project = lock_project(db, project_id)  # saves are serialized; the version check runs under the lock
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    _guard_draft_write(project, if_match)
    if project.status != ProjectStatus.draft:
        raise HTTPException(status_code=409, detail="Eligibility can only be changed while the requirement is a draft.")
    project.provider_eligibility = validate_rules(db, payload, project)
    db.commit()
    db.refresh(project)
    return _serialize_detail(project, db)


@router.get("/{project_id}/eligibility", response_model=EligibilityCheckOut)
def my_eligibility(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """A provider's standing against one requirement, and why. Available at
    the same level as the feed listing (platform-verified), so a provider who
    can't open the full requirement can still see the reason."""
    sync_expired_projects(db)
    project = db.get(Project, project_id)
    if not project or project.status == ProjectStatus.draft:
        raise HTTPException(status_code=404, detail="Project not found.")
    profile = acting_profile(db, user)
    if project.is_suspended:
        # Stage 4.5: say it's unavailable for now -- nothing about it, or why.
        return EligibilityCheckOut(eligible=False, rules=ProviderEligibilityOut(provider_type="any", qualifications=[], match_category=False, match_governorate=False), participation=participation(db, project, profile))
    reasons = ineligibility_reasons(db, project, profile)
    listing = None
    if project.status == ProjectStatus.open and project.bid_deadline > datetime.utcnow():  # open (paused or not), as the feed shows it
        listing = OpportunityListing(
            title=project.title, trade=project.trade, governorate=project.governorate, area=project.area,
            bid_deadline=project.bid_deadline, tender_type=project.tender_type, published_at=project.published_at,
            paused=project.paused_at is not None,
        )
    return EligibilityCheckOut(
        eligible=not reasons, reasons=reasons, rules=rules_out(db, project), listing=listing, participation=participation(db, project, profile, reasons)
    )


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


@router.get("/{project_id}/versions/{number}", response_model=RequirementVersionOut)
def get_version(project_id: str, number: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stage 3.17: the requirement as it stood at a material version -- 0 is
    as published, N as after the Nth material amendment -- with the documents
    current then. Rebuilt from today's record by undoing, newest first, the
    recorded before/after of every amendment from the next version on; so an offer made against
    version N can be read against exactly what it priced. Same visibility as
    the requirement itself."""
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.published_at is None or not 0 <= number <= project.material_revision:
        raise HTTPException(status_code=404, detail="No such version.")
    amendments = db.query(ProjectAmendment).filter(ProjectAmendment.project_id == project_id).order_by(ProjectAmendment.amendment_number.desc()).all()
    start = next((a for a in amendments if a.material and a.material_revision == number), None) if number else None
    following = next((a for a in reversed(amendments) if a.material and a.material_revision == number + 1), None)
    fields = {f: _plain(getattr(project, f)) for f in TRACKED_FIELDS}
    complete = True
    # Version N as it last stood (its non-material corrections included):
    # undo everything from the amendment that started version N+1 on.
    for a in amendments:
        if following is None or a.amendment_number < following.amendment_number:
            break
        if a.changes is None:
            complete = False  # recorded before 3.17: what it replaced wasn't kept
            continue
        for field, change in a.changes.items():
            if field in fields:
                fields[field] = change["from"]
    # The documents then: of each file, its latest revision brought in by this version or before.
    current: dict[str, ProjectDrawing] = {}
    for d in db.query(ProjectDrawing).filter(ProjectDrawing.project_id == project_id).order_by(ProjectDrawing.revision.asc()):
        if d.material_revision <= number:
            current[d.file_name.lower()] = d
    storage = get_storage()
    expiry = drawing_url_expiry_seconds(project.bid_deadline)
    return RequirementVersionOut(
        number=number,
        current=number == project.material_revision,
        complete=complete,
        effective_from=start.created_at if start else project.published_at,
        superseded_at=following.created_at if following else None,
        amendment_number=start.amendment_number if start else None,
        fields=fields,
        documents=[
            DrawingOut(
                id=d.id, file_name=d.file_name, uploaded_at=d.uploaded_at, revision=d.revision, is_current=d.is_current,
                category=d.category, is_required=d.is_required, size_bytes=d.size_bytes, url=storage.signed_url("project-drawings", d.file_path, expiry, d.file_name),
            )
            for d in sorted(current.values(), key=lambda d: d.file_name.lower())
        ],
    )


# ---------- Stage 4.9: the decision to take part ----------

def _decision(db: Session, user: User, project: Project) -> ParticipationRecord | None:
    return db.query(ParticipationRecord).filter(
        ParticipationRecord.project_id == project.id, mine(db, user, ParticipationRecord, ParticipationRecord.service_provider_id)
    ).first()


def _with_decision(db: Session, user: User, project: Project, verdict) -> None:
    record = _decision(db, user, project)
    if record:
        verdict.started, verdict.started_at, verdict.seen_material_revision = True, record.started_at, record.seen_material_revision


def record_decision(db: Session, user: User, project: Project) -> None:
    """Record that this provider takes part (idempotent: one per provider and
    requirement) at the requirement's current version. Used by Participate
    and by every offer submitted. The caller commits."""
    record = _decision(db, user, project)
    if record is None:
        db.add(ParticipationRecord(
            project_id=project.id, service_provider_id=acting_id(db, user), organization_id=org_of(db, user.id),
            started_by=user.id, seen_material_revision=project.material_revision,
        ))
    else:
        record.seen_material_revision = project.material_revision


_NOT_NOW = {
    "paused": "This requirement is paused by its owner; you can take part once it resumes.",
    "ended": "This requirement is no longer accepting offers.",
    "unavailable": "This requirement is temporarily unavailable.",
}


def _deadline_ended(project: Project) -> bool:
    """Stage 5.1: offers stopped because the response deadline passed (by the
    server's clock) -- as opposed to the owner ending it early."""
    if project.bid_deadline > datetime.utcnow():
        return False
    if project.status == ProjectStatus.open:
        return True
    stopped = project.closed_at
    return project.status in (ProjectStatus.closed, ProjectStatus.expired) and (stopped is None or stopped >= project.bid_deadline)


@router.post("/{project_id}/participate", response_model=ParticipationOut)
def participate(project_id: str, user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    """Stage 4.9: the provider decides to take part -- from evaluating the
    opportunity to preparing an offer. Allowed only when every condition
    holds now, judged under the requirement's lock (the same lock a close,
    a pause or the deadline sync takes): open and before its deadline, the
    provider verified with marketplace access, and eligible. Each refusal
    says why. Doing it again records nothing new; after a material change it
    marks the provider as having seen the current version. Nothing is sent
    to the owner."""
    sync_expired_projects(db)
    project = lock_project(db, project_id)
    if not project or project.status == ProjectStatus.draft:
        raise HTTPException(status_code=404, detail="Project not found.")
    profile = acting_profile(db, user)
    reasons = ineligibility_reasons(db, project, profile) if profile else []
    verdict = participation(db, project, profile, reasons)
    if verdict.status == "unavailable":
        detail = _NOT_NOW[verdict.availability]
        if verdict.availability == "ended" and _deadline_ended(project):
            detail += " Its response deadline has passed."
        raise HTTPException(status_code=400, detail=detail)
    if verdict.status == "action_required":
        detail = {
            "activate_access": "Activate your marketplace access to take part.",
            "account_suspended": "Your account is suspended, so you can't take part in opportunities. Contact support.",
        }.get(verdict.action, "Complete your verification to take part in opportunities.")
        raise HTTPException(status_code=403, detail=detail)
    if verdict.status == "not_eligible":
        raise HTTPException(status_code=403, detail="You aren't eligible to respond to this requirement. " + " ".join(r.message for r in reasons))
    record_decision(db, user, project)
    try:
        db.commit()
    except IntegrityError:  # the same decision from another request at the same moment
        db.rollback()
    _with_decision(db, user, project, verdict)
    return verdict


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
    # Stage 3.6: what these files are, and whether providers need them to
    # price the work (applies to every file in this upload).
    category: str = Form("drawing"),
    is_required: bool = Form(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = lock_project(db, project_id)  # saves are serialized; the version check runs under the lock
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    _require_active_owner(user, db)
    _guard_draft_write(project, None)
    if category not in DOCUMENT_CATEGORIES:
        raise HTTPException(status_code=400, detail="Unknown document type.")
    published = project.status != ProjectStatus.draft
    if published:
        # Stage 3.15: a document added after publication changes what
        # providers price -- only while offers are open, with time to react,
        # and recorded and announced as an amendment.
        if project.status != ProjectStatus.open:
            raise HTTPException(status_code=400, detail="This project can no longer be amended.")
        if project.bid_deadline - datetime.utcnow() < MATERIAL_NOTICE:
            raise HTTPException(
                status_code=400,
                detail="A change to what providers price needs at least 3 days before offers close. Extend the deadline in the same change.",
            )

    real_files = [f for f in drawings if f.filename]
    existing = {d.id for d in db.query(ProjectDrawing.id).filter(ProjectDrawing.project_id == project_id)}
    await upload_drawings_for_project(db, get_storage(), project_id, real_files, category, is_required)
    db.commit()
    if published:
        # Stage 3.17: a same-named file replaces the current one as a new
        # revision; the old one stays, tied to the version it belonged to.
        new = [d for d in db.query(ProjectDrawing).filter(ProjectDrawing.project_id == project_id) if d.id not in existing]
        if new:
            documents = {
                "added": sorted(d.file_name for d in new if d.revision == 1),
                "replaced": sorted(d.file_name for d in new if d.revision > 1),
            }
            _record_amendment(
                db, project, user, ["documents"], None,  # the files are in `changes`
                changes={"documents": documents}, documents=new,
            )
    db.refresh(project)
    return _serialize_detail(project, db)


def _owned_draft_document(project_id: str, drawing_id: str, user: User, db: Session) -> tuple[Project, ProjectDrawing]:
    project = lock_project(db, project_id)  # saves are serialized; the version check runs under the lock
    drawing = db.get(ProjectDrawing, drawing_id)
    if not project or not owns(db, user, project) or not drawing or drawing.project_id != project_id:
        raise HTTPException(status_code=404, detail="Document not found.")
    _require_active_owner(user, db)
    _guard_draft_write(project, None)
    if project.status != ProjectStatus.draft:
        # Once published, providers may already be pricing against a file;
        # replace it by uploading a new revision instead.
        raise HTTPException(status_code=409, detail="Documents can only be removed or re-labelled while the requirement is a draft.")
    return project, drawing


class DocumentPatch(BaseModel):
    category: str | None = None
    is_required: bool | None = None


@router.patch("/{project_id}/drawings/{drawing_id}", response_model=ProjectDetailOut)
def update_document(
    project_id: str, drawing_id: str, payload: DocumentPatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    project, drawing = _owned_draft_document(project_id, drawing_id, user, db)
    if payload.category is not None:
        if payload.category not in DOCUMENT_CATEGORIES:
            raise HTTPException(status_code=400, detail="Unknown document type.")
        drawing.category = payload.category
    if payload.is_required is not None:
        drawing.is_required = payload.is_required
    db.commit()
    db.refresh(project)
    return _serialize_detail(project, db)


@router.delete("/{project_id}/drawings/{drawing_id}", response_model=ProjectDetailOut)
def remove_document(project_id: str, drawing_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Removes a document from a draft, with all its earlier revisions (rows
    sharing its file name) and their stored files."""
    project, drawing = _owned_draft_document(project_id, drawing_id, user, db)
    versions = (
        db.query(ProjectDrawing)
        .filter(ProjectDrawing.project_id == project_id, ProjectDrawing.file_name.ilike(drawing.file_name))
        .all()
    )
    paths = [v.file_path for v in versions]
    for v in versions:
        db.delete(v)
    db.commit()
    try:
        get_storage().delete("project-drawings", paths)
    except Exception:
        pass  # the records are gone; an unreferenced stored file is unreachable
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
            category=d.category,
            is_required=d.is_required,
            size_bytes=d.size_bytes,
            url=storage.signed_url("project-drawings", d.file_path, expiry, d.file_name),
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
            category=d.category,
            is_required=d.is_required,
            size_bytes=d.size_bytes,
            url=storage.signed_url("project-drawings", d.file_path, expiry, d.file_name),
        )
        for d in drawing_rows
    ]
    return ProjectDetailOut(
        id=project.id,
        owner_id=project.owner_id,
        title=project.title,
        address=project.address,
        governorate=project.governorate,
        area=project.area,
        description=project.description,
        trade=project.trade,
        category_id=project.category_id,
        bid_deadline=project.bid_deadline,
        expected_start_date=project.expected_start_date,
        expected_completion_date=project.expected_completion_date,
        expected_duration_days=project.expected_duration_days,
        status=project.status,
        tender_type=project.tender_type,
        tender_type_locked=project.tender_type_locked,
        is_suspended=project.is_suspended,
        created_at=project.created_at,
        updated_at=project.updated_at,
        discarded_at=project.discarded_at,
        published_at=project.published_at,
        paused_at=project.paused_at,
        pause_reason=project.pause_reason,
        closed_at=project.closed_at,
        material_revision=project.material_revision,
        closure_reason=project.closure_reason,
        version=project.version,
        documents_required=project.documents_required,
        offer_count=offer_count,
        drawings=drawings,
        pricing_basis=project.pricing_basis,
        items=[ProjectItemOut.model_validate(i) for i in project.items],
        provider_eligibility=rules_out(db, project),
        tender_rules=TenderRulesOut(
            questions_allowed=project.questions_allowed,
            questions_deadline=project.questions_deadline,
            questions_close_at=questions_close_at(project),
            questions_open=questions_open(project),
            commercial_conditions=CommercialConditions(**(project.commercial_conditions or {})),
            commercial_terms=project.commercial_terms,
            bidder_instructions=project.bidder_instructions,
        ),
        response_requirements=ResponseRequirements(**(project.response_requirements or {})),
        currency=get_settings().marketplace_currency,
    )
