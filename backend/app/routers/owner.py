from datetime import datetime

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_owner_profile, require_owner
from app.models.award_record import AwardRecord
from app.models.service_provider import ServiceProviderProfile
from app.models.document import DocumentRequirement
from app.models.enums import DocumentStatus, NotificationType, OfferStatus, ProjectStatus, UserRole
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.project import Project
from app.models.review import Review
from app.models.user import User
from app.schemas.document import DocumentRequirementOut, OwnerDocumentOut
from app.schemas.offer import OfferOut, OfferRevisionOut
from app.schemas.owner import OwnerProfileOut
from app.schemas.project import EligibilityQualification, ProjectOut
from app.schemas.review import ReviewCreate, ReviewOut
from app.services.audit import log_action
from app.services.email import notify_service_provider_offer_decision
from app.services.file_security import ALLOWED_DOCUMENT_EXTENSIONS, assert_allowed_extension, sanitize_path_segment
from app.services.notify import notify, notify_team
from app.services.team import acting_profile, mine, owns
from app.services.eligibility import qualification_options
from app.services.offer_response import documents_out
from app.services.stakeholder import require_established
from app.services.verification import (
    applicable_requirements,
    assert_editable,
    assert_ready_to_submit,
    checklist,
    document_out_fields,
    mark_submitted,
    profile_state_fields,
)
from app.services.storage import get_storage
from app.services.tender_lifecycle import is_sealed_and_open, lock_project, publish, sync_expired_projects

router = APIRouter(prefix="/owner", tags=["owner"])


@router.get("/eligibility-qualifications", response_model=list[EligibilityQualification])
def eligibility_qualifications(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 3.9: the provider documents the platform verifies, which an owner
    may require for a particular requirement. Managed by admins (Document
    requirements); nothing is hard-coded."""
    return [EligibilityQualification(id=r.id, name=r.name, description=r.description) for r in qualification_options(db)]


def _get_owned_project(project_id: str, user: User, db: Session, *, lock: bool = False) -> Project:
    # lock=True for anything that CHANGES the tender's state: take the tender
    # row lock first and judge the state under it (see lock_project), so two
    # transitions at once -- close vs cancel, award vs award, award vs a bid
    # -- are serialized instead of both passing a stale check.
    project = lock_project(db, project_id) if lock else db.get(Project, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    if lock:
        # A suspended (or unapproved) owner keeps read access to their tender
        # but can't change its state or award it -- the same rule and code as
        # require_verified_owner, checked after ownership so everyone else
        # still gets the 404 they always did.
        profile = acting_profile(db, user)
        if not profile or not profile.is_verified_active:
            raise HTTPException(status_code=403, detail="not_approved")
    return project


@router.get("/projects", response_model=list[ProjectOut])
def dashboard(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    sync_expired_projects(db)
    projects = (
        db.query(Project)
        # A discarded draft is no longer one of the owner's active requirements.
        # The organization's requirements, whoever in it started them.
        .filter(mine(db, user, Project, Project.owner_id), Project.discarded_at.is_(None))
        .order_by(Project.created_at.desc())
        .all()
    )
    out = []
    for p in projects:
        offer_count = db.query(Offer).filter(Offer.project_id == p.id).count()
        out.append(ProjectOut(**_project_fields(p), offer_count=offer_count))
    return out


@router.get("/projects/{project_id}/offers", response_model=list[OfferOut])
def list_offers(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    project = _get_owned_project(project_id, user, db)
    sealed = is_sealed_and_open(project)

    # An admin-suspended offer is withheld from the owner's evaluation view
    # entirely (not just non-awardable) — the same "pull it out of sight
    # until an admin reactivates it" moderation intent as a suspended
    # project, applied per-bid instead of per-project.
    query = (
        db.query(Offer, ServiceProviderProfile)
        .join(ServiceProviderProfile, Offer.service_provider_id == ServiceProviderProfile.user_id)
        .filter(Offer.project_id == project_id, Offer.is_suspended.is_(False))
    )
    # Sorting by amount would itself leak relative ranking on a sealed
    # tender (the owner could infer who's cheapest from list order alone
    # even with the amounts blanked out) — order by submission time instead
    # while sealed, by amount once the seal is lifted for real evaluation.
    query = query.order_by(Offer.created_at.asc()) if sealed else query.order_by(Offer.amount.asc())
    offers = query.all()

    if sealed:
        # Bidder identity, amount, message, and rating are all withheld —
        # only enough to show "N bids are in" (spec §19-21, D-001). Every
        # field a curious owner could use to single out a bidder stays None.
        return [
            OfferOut(
                id=o.id,
                project_id=o.project_id,
                service_provider_id=None,
                amount=None,
                timeline_estimate=None,
                message=None,
                status=o.status,
                revision=o.revision,
            based_on_material_revision=o.based_on_material_revision,
                created_at=o.created_at,
                updated_at=o.updated_at,
                sealed=True,
            )
            for o, _cp in offers
        ]

    return [
        OfferOut(
            id=o.id,
            project_id=o.project_id,
            service_provider_id=o.service_provider_id,
            amount=o.amount,
            timeline_estimate=o.timeline_estimate,
            message=o.message,
            item_prices=o.item_prices,
            assumptions=o.assumptions,
            declarations_accepted=o.declarations_accepted,
            documents=documents_out(db, project_id, o.organization_id, o.service_provider_id),
            status=o.status,
            revision=o.revision,
            based_on_material_revision=o.based_on_material_revision,
            created_at=o.created_at,
            updated_at=o.updated_at,
            service_provider_company_name=cp.company_name,
            service_provider_avg_rating=cp.avg_rating,
            service_provider_review_count=cp.review_count,
        )
        for o, cp in offers
    ]


@router.get("/projects/{project_id}/offers/{offer_id}/history", response_model=list[OfferRevisionOut])
def offer_history(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    project = _get_owned_project(project_id, user, db)
    if is_sealed_and_open(project):
        # Same rule as the list itself — a per-bid revision trail is just
        # as identifying as the current amount, so it stays hidden until
        # the seal lifts.
        raise HTTPException(status_code=404, detail="Not available while this tender is sealed and still open.")

    offer = db.get(Offer, offer_id)
    if not offer or offer.project_id != project_id:
        raise HTTPException(status_code=404, detail="Offer not found.")

    return (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer_id)
        .order_by(OfferRevision.revision_number.asc())
        .all()
    )


@router.post("/projects/{project_id}/offers/{offer_id}/approve", response_model=ProjectOut)
def approve_offer(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    # Awarding is only meaningful once bidding has actually stopped — the
    # full lifecycle (spec §2.12) makes "open" and "draft" ineligible, not
    # just "already awarded". A deadline that just passed is caught by the
    # sync_expired_projects() call above before this check runs.
    if project.status not in (ProjectStatus.closed, ProjectStatus.under_evaluation):
        detail = (
            "This project has already been awarded, canceled, or has no award."
            if project.status in (ProjectStatus.awarded, ProjectStatus.canceled, ProjectStatus.no_award, ProjectStatus.expired)
            else "Close bidding before awarding an offer."
        )
        raise HTTPException(status_code=400, detail=detail)

    winning_offer = db.get(Offer, offer_id)
    if not winning_offer or winning_offer.project_id != project_id:
        raise HTTPException(status_code=404, detail="Offer not found.")
    if winning_offer.status != OfferStatus.submitted:
        raise HTTPException(status_code=400, detail="Only a live bid can be awarded.")
    if winning_offer.is_suspended:
        raise HTTPException(status_code=400, detail="This offer has been suspended by an admin and cannot be awarded.")

    # Only other LIVE bids get marked rejected — a bid the service provider
    # already withdrew stays withdrawn, not overwritten into a status that
    # never actually happened.
    other_offers = (
        db.query(Offer)
        .filter(Offer.project_id == project_id, Offer.id != offer_id, Offer.status == OfferStatus.submitted)
        .all()
    )

    winning_offer.status = OfferStatus.approved
    winning_offer.updated_at = datetime.utcnow()
    for o in other_offers:
        o.status = OfferStatus.rejected
        o.updated_at = datetime.utcnow()
    project.status = ProjectStatus.awarded

    # Permanent record (spec §34, §87) — snapshots exactly which revision
    # of the tender and of the winning bid were in effect at award time, so
    # it stays meaningful even after later amendments or a hypothetical bid
    # edit (bids can't be edited post-close, but the tender's own revision
    # can still move via future passes' evaluation tooling).
    db.add(
        AwardRecord(
            project_id=project_id,
            offer_id=winning_offer.id,
            service_provider_id=winning_offer.service_provider_id,
            amount=winning_offer.amount,
            project_revision=project.revision,
            offer_revision=winning_offer.revision,
            awarded_by=user.id,
        )
    )
    # log_action commits: the award, the status changes and the audit row land
    # in ONE transaction, so there is no committed award without its audit entry.
    log_action(
        db,
        actor_id=user.id,
        action="project.award",
        target_type="project",
        target_id=project_id,
        new_value=f"offer:{winning_offer.id} service_provider:{winning_offer.service_provider_id} amount:{winning_offer.amount}",
    )

    # Best-effort — notification failures never roll back the award itself.
    winner_user = db.get(User, winning_offer.service_provider_id)
    if winner_user:
        notify_service_provider_offer_decision(winner_user.email, project.title, approved=True)
        notify_team(db, winner_user, NotificationType.award_won, link=f"/service-provider/projects/{project_id}/offer", organization_id=winning_offer.organization_id, project_title=project.title)
    for o in other_offers:
        loser_user = db.get(User, o.service_provider_id)
        if loser_user:
            notify_service_provider_offer_decision(loser_user.email, project.title, approved=False)
            notify_team(db, loser_user, NotificationType.award_lost, link=f"/service-provider/projects/{project_id}/offer", organization_id=o.organization_id, project_title=project.title)

    db.refresh(project)
    offer_count = db.query(Offer).filter(Offer.project_id == project_id).count()
    return ProjectOut(**_project_fields(project), offer_count=offer_count)


# ---------- lifecycle actions (spec §2.12 full tender lifecycle) ----------
# Every transition below is an explicit owner decision; the only automatic
# one is open -> closed/expired, handled lazily by sync_expired_projects.

def _project_response(project: Project, db: Session) -> ProjectOut:
    offer_count = db.query(Offer).filter(Offer.project_id == project.id).count()
    return ProjectOut(**_project_fields(project), offer_count=offer_count)


@router.post("/projects/{project_id}/publish", response_model=ProjectOut)
def publish_project(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    project = _get_owned_project(project_id, user, db, lock=True)
    publish(db, project, user.id)  # the one publication transition (tender_lifecycle)
    db.refresh(project)
    return _project_response(project, db)


@router.post("/projects/{project_id}/close", response_model=ProjectOut)
def close_project(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Manually stop accepting bids before the deadline — e.g. the owner is
    satisfied with what's in hand and wants to move straight to evaluation."""
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status != ProjectStatus.open:
        raise HTTPException(status_code=400, detail="Only an open project can be closed.")
    # Closing lifts the seal (is_sealed_and_open turns false), so an owner who
    # could close early could read every sealed bid before the deadline.
    # Sealed tenders open only when their deadline passes.
    if is_sealed_and_open(project) and project.bid_deadline > datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail="A sealed tender can't be closed early \u2014 its bids stay sealed until the deadline. "
            "Cancel the tender instead if you no longer want bids.",
        )
    # Stage 3.15: the authoritative closure time, an audit entry, and the
    # bidders told. Every offer stays exactly as submitted.
    now = datetime.utcnow().replace(microsecond=0)
    project.status = ProjectStatus.closed
    project.closed_at = now
    project.paused_at = None
    log_action(db, actor_id=user.id, action="project.close", target_type="project", target_id=project_id, previous_value="open", new_value="closed")
    _notify_bidders(db, project, NotificationType.tender_closed)
    db.refresh(project)
    return _project_response(project, db)


class PauseRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/projects/{project_id}/pause", response_model=ProjectOut)
def pause_project(project_id: str, payload: PauseRequest, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 3.15: the owner keeps the requirement but stops participation for
    now. Providers see it is paused, and why; nothing is accepted (offers,
    revisions, withdrawals, attachments, questions) until it resumes.
    Offers, documents and history are untouched. The deadline still runs:
    extend it (an amendment) if the pause will outlast it."""
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status != ProjectStatus.open:
        raise HTTPException(status_code=400, detail="Only an open requirement can be paused.")
    if project.paused_at is not None:
        raise HTTPException(status_code=400, detail="This requirement is already paused.")
    project.paused_at = datetime.utcnow().replace(microsecond=0)
    project.pause_reason = payload.reason.strip()
    log_action(db, actor_id=user.id, action="project.pause", target_type="project", target_id=project_id, new_value=project.pause_reason)
    _notify_bidders(db, project, NotificationType.tender_paused, reason=project.pause_reason)
    db.refresh(project)
    return _project_response(project, db)


@router.post("/projects/{project_id}/resume", response_model=ProjectOut)
def resume_project(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Back to open under the same rules and the deadline as it now stands --
    never silently reopening one whose deadline has passed (it is then closed
    or expired, and stays so)."""
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status != ProjectStatus.open or project.paused_at is None:
        raise HTTPException(status_code=400, detail="Only a paused, still-open requirement can be resumed.")
    if project.bid_deadline <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="The offer deadline has passed, so this requirement can't reopen.")
    project.paused_at = None
    project.pause_reason = None
    log_action(db, actor_id=user.id, action="project.resume", target_type="project", target_id=project_id)
    _notify_bidders(db, project, NotificationType.tender_resumed, deadline=project.bid_deadline.strftime("%d %b %Y %H:%M UTC"))
    db.refresh(project)
    return _project_response(project, db)


@router.post("/projects/{project_id}/start-evaluation", response_model=ProjectOut)
def start_evaluation(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status != ProjectStatus.closed:
        raise HTTPException(status_code=400, detail="Only a closed project can enter evaluation.")
    project.status = ProjectStatus.under_evaluation
    db.commit()
    db.refresh(project)
    return _project_response(project, db)


def _notify_bidders(db: Session, project: Project, notification_type: NotificationType, **details) -> None:
    bidders = (
        db.query(Offer.service_provider_id, Offer.organization_id)
        .filter(Offer.project_id == project.id, Offer.status != OfferStatus.withdrawn)
        .distinct()
        .all()
    )
    for service_provider_id, organization_id in bidders:
        bidder = db.get(User, service_provider_id)
        if bidder:
            notify_team(
                db,
                bidder,
                notification_type,
                link=f"/service-provider/projects/{project.id}/offer",
                organization_id=organization_id,
                project_title=project.title,
                **details,
            )


@router.post("/projects/{project_id}/no-award", response_model=ProjectOut)
def mark_no_award(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status not in (ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise HTTPException(status_code=400, detail="Only a closed or under-evaluation project can be marked no-award.")
    previous = project.status.value
    project.status = ProjectStatus.no_award
    log_action(db, actor_id=user.id, action="project.no_award", target_type="project", target_id=project_id, previous_value=previous, new_value="no_award")
    _notify_bidders(db, project, NotificationType.tender_no_award)
    db.refresh(project)
    return _project_response(project, db)


@router.post("/projects/{project_id}/discard", response_model=ProjectOut)
def discard_draft(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 3.11: the owner decides not to go ahead with a draft. It stays a
    draft -- never published, so as private as ever -- marked discarded: no
    longer listed, editable or publishable. Kept (with its files) rather than
    deleted, so the audit trail still points at a record."""
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status != ProjectStatus.draft:
        raise HTTPException(status_code=400, detail="Only a draft can be discarded.")
    if project.discarded_at is not None:
        raise HTTPException(status_code=400, detail="This draft has already been discarded.")
    project.discarded_at = datetime.utcnow().replace(microsecond=0)
    log_action(db, actor_id=user.id, action="project.discard_draft", target_type="project", target_id=project_id, previous_value="draft", new_value="discarded")
    db.refresh(project)
    return _project_response(project, db)


@router.post("/projects/{project_id}/cancel", response_model=ProjectOut)
def cancel_project(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status == ProjectStatus.draft:
        # A draft was never published: "cancelling" it is discarding it. It
        # must not become a canceled tender, which providers can open.
        db.rollback()
        return discard_draft(project_id, user, db)
    if project.status not in (ProjectStatus.draft, ProjectStatus.open, ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise HTTPException(status_code=400, detail="This project can no longer be canceled.")
    previous = project.status.value
    project.status = ProjectStatus.canceled
    log_action(db, actor_id=user.id, action="project.cancel", target_type="project", target_id=project_id, previous_value=previous, new_value="canceled")
    _notify_bidders(db, project, NotificationType.tender_cancelled)
    db.refresh(project)
    return _project_response(project, db)


@router.get("/projects/{project_id}/review", response_model=ReviewOut | None)
def get_review(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    return db.query(Review).filter(Review.project_id == project_id).first()


@router.post("/reviews", response_model=ReviewOut)
def submit_review(payload: ReviewCreate, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    project = db.get(Project, payload.project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    if project.status != ProjectStatus.awarded:
        raise HTTPException(status_code=400, detail="You can only review a project after it's awarded.")

    existing = db.query(Review).filter(Review.project_id == payload.project_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="A review already exists for this project.")

    # The service provider being reviewed is derived from the project's own
    # AwardRecord, never trusted from the request body — payload.service_provider_id
    # is otherwise a free-text client-supplied ID with only a "some real
    # service provider exists" FK constraint behind it, letting an owner rate ANY
    # service provider's public profile under cover of an unrelated awarded
    # project (a real IDOR, found and fixed in PASS 17's security audit).
    award = db.query(AwardRecord).filter(AwardRecord.project_id == payload.project_id).first()
    if not award:
        raise HTTPException(status_code=400, detail="This project has no award record to review against.")

    review = Review(
        project_id=payload.project_id,
        owner_id=user.id,
        service_provider_id=award.service_provider_id,
        rating=payload.rating,
        comment=payload.comment or None,
    )
    db.add(review)
    db.commit()

    # Recompute the service provider's public average rather than trusting an
    # incrementally-maintained counter, so it can never drift out of sync.
    # Uses the same server-derived award.service_provider_id as above — never
    # payload.service_provider_id.
    all_reviews = db.query(Review.rating).filter(Review.service_provider_id == award.service_provider_id).all()
    review_count = len(all_reviews)
    avg_rating = round(sum(r[0] for r in all_reviews) / review_count, 1) if review_count else 0

    profile = db.get(ServiceProviderProfile, award.service_provider_id)
    if profile:
        profile.avg_rating = avg_rating
        profile.review_count = review_count
        db.commit()

    db.refresh(review)
    return review


# ---------- owner verification (mirrors the service provider document-review
# flow in routers/service-provider.py, scoped to DocumentRequirement.applies_to
# == owner) ----------

@router.get("/requirements", response_model=list[DocumentRequirementOut])
def owner_active_requirements(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """The admin-configured requirements that apply to this account's
    stakeholder type right now."""
    return applicable_requirements(db, UserRole.owner, get_owner_profile(user, db).stakeholder_type)


def _owner_profile_out(op: OwnerProfile, user: User) -> OwnerProfileOut:
    return OwnerProfileOut(
        user_id=op.user_id,
        verification_status=op.verification_status,
        is_suspended=op.is_suspended,
        marketplace_status=op.marketplace_status,
        created_at=op.created_at,
        email=user.email,
        full_name=user.full_name,
        **profile_state_fields(op),
    )


@router.get("/profile", response_model=OwnerProfileOut)
def owner_verification_profile(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    profile = get_owner_profile(user, db)
    return _owner_profile_out(profile, user)


@router.get("/documents", response_model=list[OwnerDocumentOut])
def list_owner_documents(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """This account's checklist: one row per applicable requirement."""
    rows = checklist(db, get_owner_profile(user, db))
    db.commit()
    return [OwnerDocumentOut(**document_out_fields(d, r)) for r, d in rows]


@router.post("/documents/{requirement_id}/upload", response_model=OwnerDocumentOut)
async def upload_owner_document(
    requirement_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    op = get_owner_profile(user, db)
    assert_editable(op)
    doc = next((d for r, d in checklist(db, op) if r.id == requirement_id), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document requirement not found for this owner.")

    assert_allowed_extension(file.filename, ALLOWED_DOCUMENT_EXTENSIONS)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="No file provided.")

    safe_name = sanitize_path_segment(file.filename)
    path = f"{user.id}/{requirement_id}/{int(datetime.utcnow().timestamp() * 1000)}-{safe_name}"
    get_storage().save("owner-documents", path, content, file.content_type or "application/octet-stream")

    doc.file_path = path
    doc.status = DocumentStatus.pending
    doc.submitted_at = datetime.utcnow()
    doc.admin_note = None
    doc.expires_on = None
    db.commit()
    db.refresh(doc)
    return OwnerDocumentOut(**document_out_fields(doc, db.get(DocumentRequirement, requirement_id)))


@router.post("/submit-for-review", response_model=OwnerProfileOut)
def owner_submit_for_review(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    profile = get_owner_profile(user, db)
    require_established(profile)
    assert_editable(profile)
    assert_ready_to_submit(db, profile)
    mark_submitted(profile)
    db.commit()
    db.refresh(profile)
    return _owner_profile_out(profile, user)


def _project_fields(p: Project) -> dict:
    return dict(
        id=p.id,
        owner_id=p.owner_id,
        title=p.title,
        address=p.address,
        governorate=p.governorate,
        area=p.area,
        description=p.description,
        trade=p.trade,
        bid_deadline=p.bid_deadline,
        expected_start_date=p.expected_start_date,
        expected_completion_date=p.expected_completion_date,
        expected_duration_days=p.expected_duration_days,
        status=p.status,
        tender_type=p.tender_type,
        tender_type_locked=p.tender_type_locked,
        is_suspended=p.is_suspended,
        created_at=p.created_at,
        updated_at=p.updated_at,
        discarded_at=p.discarded_at,
        version=p.version,
        published_at=p.published_at,
        paused_at=p.paused_at,
        pause_reason=p.pause_reason,
        closed_at=p.closed_at,
        material_revision=p.material_revision,
    )
