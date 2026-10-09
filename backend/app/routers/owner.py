import logging
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_owner_profile, require_owner
from app.models.agreement import Agreement
from app.models.award_record import AwardRecord
from app.models.common import gen_uuid
from app.models.clarification import Clarification
from app.models.evaluation_note import EvaluationNote
from app.models.offer_shortlist import OfferShortlist
from app.models.notification import Notification
from app.models.service_provider import ServiceProviderProfile
from app.models.document import DocumentRequirement
from app.models.enums import DocumentStatus, NotificationType, OfferStatus, ProjectStatus, UserRole
from app.models.offer import Offer, OfferRevision, tendered
from app.models.owner import OwnerProfile
from app.models.project import Project, ProjectDrawing, ProjectItem
from app.models.user import User
from app.schemas.clarification import OfferClarificationAsk, OfferClarificationOut
from app.schemas.document import DocumentRequirementOut, OwnerDocumentOut
from app.schemas.offer import ShortlistOut, EvaluationNoteEdit, EvaluationNoteIn, EvaluationNoteOut, OfferComparisonOut, OfferOut, OfferRevisionOut, OwnerOfferOut
from app.schemas.owner import OwnerProfileOut
from app.schemas.project import EligibilityQualification, ProjectOut
from app.schemas.review import OwnerReputationOut, PreviousProviderOut, ProviderReputationOut, ReceivedReviewOut, ReviewCreate, ReviewOut, ReviewReportCreate, ReviewReportOut, ReviewResponseCreate
from app.services.audit import log_action
from app.services.reviews import OWNER_TO_PROVIDER, PROVIDER_TO_OWNER, record_response, record_review, report, review_of, shown_review_of
from app.services.email import notify_provider_requirement_ended, notify_service_provider_offer_decision
from app.services.file_security import ALLOWED_DOCUMENT_EXTENSIONS, assert_allowed_extension, sanitize_path_segment
from app.services.notify import notify, notify_team
from app.services.team import acting_profile, mine, owns
from app.services.eligibility import qualification_options
from app.services.offer_clarifications import clarification_out, offer_clarifications
from app.services.offer_clarifications import closed_reason as clarification_closed_reason
from app.services.offer_response import history_out, offer_file, open_file, submitted_documents_out, timing_conflicts
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
from app.services.tender_lifecycle import interested_providers, is_sealed_and_open, lock_project, publish, sync_expired_projects

logger = logging.getLogger(__name__)

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
        # Stage 6.3: the offers the owner's inbox lists (an admin-suspended one is withheld from it).
        offer_count = db.query(Offer).filter(Offer.project_id == p.id, tendered(), Offer.is_suspended.is_(False)).count()
        out.append(ProjectOut(**_project_fields(p), offer_count=offer_count))
    return out


def _owner_offer_out(db: Session, project: Project, o: Offer, cp: ServiceProviderProfile | None) -> OfferOut:
    """A live (not withdrawn) offer, in full, as the owner receives it once unsealed."""
    return OfferOut(
        id=o.id,
        project_id=o.project_id,
        service_provider_id=o.service_provider_id,
        amount=o.amount,
        timeline_estimate=o.timeline_estimate,
        # Stage 5.5: the commitment, and where it differs from what the owner expects (sealed: withheld above).
        proposed_start_date=o.proposed_start_date,
        proposed_completion_date=o.proposed_completion_date,
        proposed_duration_days=o.proposed_duration_days,
        timing_conflicts=timing_conflicts(project, o),
        message=o.message,
        item_prices=o.item_prices,
        assumptions=o.assumptions,
        declarations_accepted=o.declarations_accepted,
        documents=submitted_documents_out(db, o),  # Stage 5.13: as submitted, not mid-revision
        status=o.status,
        revision=o.revision,
        based_on_material_revision=o.based_on_material_revision,
        submitted_at=o.submitted_at,
        created_at=o.created_at,
        updated_at=o.updated_at,
        service_provider_company_name=cp.company_name if cp else None,
        service_provider_avg_rating=cp.avg_rating if cp else None,
        service_provider_review_count=cp.review_count if cp else None,
        shortlisted=db.query(OfferShortlist.id).filter(OfferShortlist.offer_id == o.id).first() is not None,  # Stage 6.12
    )


@router.get("/projects/{project_id}/offers", response_model=list[OfferOut])
def list_offers(
    project_id: str,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
    # Stage 6.1: bounded, as "my bids" is -- each row signs its documents' links.
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    project = _get_owned_project(project_id, user, db)
    sealed = is_sealed_and_open(project)

    # An admin-suspended offer is withheld from the owner's evaluation view
    # entirely (not just non-awardable) — the same "pull it out of sight
    # until an admin reactivates it" moderation intent as a suspended
    # project, applied per-bid instead of per-project.
    query = (
        db.query(Offer, ServiceProviderProfile)
        .join(ServiceProviderProfile, Offer.service_provider_id == ServiceProviderProfile.user_id)
        .filter(Offer.project_id == project_id, Offer.is_suspended.is_(False), tendered())
    )
    # In the order offers came in -- never by amount: on a sealed tender list
    # order alone would leak who is cheapest, and once open, a list ranked by
    # price would be the platform ranking offers (Stage 6.7: the owner
    # weighs them; nothing here orders them by merit). Stage 6.1: live offers
    # ahead of withdrawn ones, the offer id last so ties keep one order
    # across refreshes and pages.
    live_first = case((Offer.status == OfferStatus.withdrawn, 1), else_=0)
    query = query.order_by(Offer.submitted_at.asc(), Offer.id) if sealed else query.order_by(live_first, Offer.submitted_at.asc(), Offer.id)
    offers = query.offset(offset).limit(limit).all()

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
                submitted_at=o.submitted_at,
                created_at=o.created_at,
                updated_at=o.updated_at,
                sealed=True,
            )
            for o, _cp in offers
        ]

    # Stage 6.2: a withdrawn offer is no longer one the owner may consider --
    # they see who withdrew and when, never its content. Otherwise a sealed
    # offer withdrawn before the deadline would be opened at the deadline.
    out = [
        OfferOut(
            id=o.id,
            project_id=o.project_id,
            service_provider_id=o.service_provider_id,
            amount=None,
            timeline_estimate=None,
            message=None,
            status=o.status,
            revision=o.revision,
            based_on_material_revision=o.based_on_material_revision,
            submitted_at=o.submitted_at,
            created_at=o.created_at,
            updated_at=o.updated_at,
            service_provider_company_name=cp.company_name,
            service_provider_avg_rating=cp.avg_rating,
            service_provider_review_count=cp.review_count,
        )
        if o.status == OfferStatus.withdrawn
        else _owner_offer_out(db, project, o, cp)
        for o, cp in offers
    ]
    return _with_track_record(db, project, out)


def _with_track_record(db: Session, project: Project, out: list[OfferOut]) -> list[OfferOut]:
    """Stage 8.12/8.14: beside each unsealed offer, its provider's completed
    U-Tender transactions and those completed with this owner organisation
    -- two grouped queries for the whole page, from the authoritative
    records. Information for the owner only: it never changes which offers
    are shown, their order, or anything they are judged on."""
    from app.services.reputation import completed_counts, completed_together

    ids = [o.service_provider_id for o in out if o.service_provider_id]
    completed, together = completed_counts(db, ids), completed_together(db, project.owner_id, ids)
    for o in out:
        o.service_provider_completed_transactions = completed.get(o.service_provider_id, 0)
        o.completed_with_you = together.get(o.service_provider_id, 0)
    return out


def _readable_offer(project_id: str, offer_id: str, user: User, db: Session) -> Offer:
    """An offer on the owner's requirement whose content the owner may read now."""
    project = _get_owned_project(project_id, user, db)
    if is_sealed_and_open(project):
        # Same rule as the list itself — a per-bid revision trail is just
        # as identifying as the current amount, so it stays hidden until
        # the seal lifts.
        raise HTTPException(status_code=404, detail="Not available while this tender is sealed and still open.")

    offer = db.get(Offer, offer_id)
    # Stage 6.1: an admin-suspended offer is withheld from the owner (see
    # list_offers) -- its id doesn't open it either.
    # Stage 6.2: nor does a withdrawn offer (its content stays the provider's).
    if not offer or offer.project_id != project_id or offer.status in (OfferStatus.draft, OfferStatus.withdrawn) or offer.is_suspended:
        raise HTTPException(status_code=404, detail="Offer not found.")
    return offer


# Stage 6.6: how many offers one comparison takes -- enough to weigh them,
# bounded so a comparison never loads a whole inbox (each signs its links).
COMPARE_MAX = 10


@router.get("/projects/{project_id}/offers/compare", response_model=OfferComparisonOut)
def compare_offers(
    project_id: str,
    ids: list[str] = Query(..., min_length=1),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Stage 6.6: chosen offers on the owner's own requirement, side by side,
    each exactly as submitted (nothing recalculated, normalised or scored).
    The same access rules as reviewing one offer: the owner side, this
    requirement, unsealed, live (not withdrawn), not suspended. Read-only."""
    from app.routers.offers import preview_requirement

    wanted = list(dict.fromkeys(ids))  # the order chosen, each once
    if len(wanted) > COMPARE_MAX:
        raise HTTPException(status_code=400, detail=f"Compare up to {COMPARE_MAX} offers at a time.")
    project = _get_owned_project(project_id, user, db)
    if is_sealed_and_open(project):
        raise HTTPException(status_code=404, detail="Not available while this tender is sealed and still open.")
    rows = {
        o.id: (o, cp)
        for o, cp in db.query(Offer, ServiceProviderProfile)
        .outerjoin(ServiceProviderProfile, Offer.service_provider_id == ServiceProviderProfile.user_id)
        .filter(
            Offer.id.in_(wanted), Offer.project_id == project_id, Offer.is_suspended.is_(False),
            Offer.status.notin_([OfferStatus.draft, OfferStatus.withdrawn]),
        )
    }
    return OfferComparisonOut(
        requirement=preview_requirement(db, project),
        offers=_with_track_record(db, project, [_owner_offer_out(db, project, *rows[i]) for i in wanted if i in rows]),
        unavailable=[i for i in wanted if i not in rows],
    )


@router.get("/projects/{project_id}/offers/{offer_id}/history", response_model=list[OfferRevisionOut])
def offer_history(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    _readable_offer(project_id, offer_id, user, db)
    return history_out(db, db.query(OfferRevision).filter(OfferRevision.offer_id == offer_id).order_by(OfferRevision.revision_number.asc()), "owner", project_id)


@router.get("/projects/{project_id}/offers/{offer_id}", response_model=OwnerOfferOut)
def offer_detail(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 6.4: one offer, for its requirement's owner to review -- the same
    stored record and the same access rules as the inbox (unsealed, live, not
    suspended, the owner's own requirement), beside the requirement it
    answers. Read-only."""
    from app.routers.offers import preview_requirement

    offer = _readable_offer(project_id, offer_id, user, db)
    project = db.get(Project, project_id)
    cp = db.get(ServiceProviderProfile, offer.service_provider_id)
    return OwnerOfferOut(
        requirement=preview_requirement(db, project),
        provider_name=cp.company_name if cp else None,
        offer=_owner_offer_out(db, project, offer, cp),
        on_current_version=offer.based_on_material_revision >= project.material_revision,
    )


@router.get("/projects/{project_id}/offers/{offer_id}/reputation", response_model=ProviderReputationOut)
def offer_provider_reputation(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 8.7: the U-Tender reputation of the provider behind an offer, for
    the owner weighing it -- the same access rules as the offer itself
    (the owner's requirement, unsealed, live, not suspended). The provider is
    the offer's, never one named in the request. Informational only."""
    from app.services.reputation import completed_together, provider_reputation

    provider_id = _readable_offer(project_id, offer_id, user, db).service_provider_id
    out = provider_reputation(db, provider_id)
    # Stage 8.12: and the work this owner organisation completed with it.
    out.completed_with_you = completed_together(db, db.get(Project, project_id).owner_id, [provider_id]).get(provider_id, 0)
    return out


@router.get("/previous-providers", response_model=list[PreviousProviderOut])
def previous_providers_of_mine(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 8.12: the providers this owner organisation has completed U-Tender
    work with (Stage 7 completion only), each once, with those requirements.
    Its own history, by current membership; no id is taken from the request.
    To work with one again, the owner publishes a new requirement as usual."""
    from app.services.reputation import previous_providers

    return previous_providers(db, get_owner_profile(user, db).user_id)


@router.get("/projects/{project_id}/offers/{offer_id}/clarifications", response_model=list[OfferClarificationOut])
def list_offer_clarifications(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 6.10: the clarifications asked about this offer, with any
    answers -- beside the offer, which they never change."""
    return offer_clarifications(db, _readable_offer(project_id, offer_id, user, db), owner_side=True)


@router.post("/projects/{project_id}/offers/{offer_id}/clarifications", response_model=OfferClarificationOut, status_code=201)
def ask_offer_clarification(
    project_id: str, offer_id: str, payload: OfferClarificationAsk, user: User = Depends(require_owner), db: Session = Depends(get_db)
):
    """Stage 6.10: ask the offer's provider to clarify it, during evaluation.
    The offer is found on this requirement only (its id and the
    requirement's are checked together); the question goes to that offer's
    side alone. A repeat of a question still waiting for its answer is the
    same question."""
    project = _get_owned_project(project_id, user, db, lock=True)  # serialized with the requirement's outcome
    offer = _readable_offer(project_id, offer_id, user, db)
    reason = clarification_closed_reason(project, offer)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question.")
    existing = (
        db.query(Clarification)
        .filter(Clarification.offer_id == offer.id, Clarification.question == question, Clarification.answer.is_(None))
        .first()
    )
    if existing:
        db.rollback()  # release the lock; nothing changed
        return clarification_out(db, existing, owner_side=True)
    clarification = Clarification(
        project_id=project_id, offer_id=offer.id, offer_revision=offer.revision,
        service_provider_id=offer.service_provider_id, organization_id=offer.organization_id,
        question=question, shared_with_all=False, asked_by=user.id,
    )
    db.add(clarification)
    db.flush()
    # log_action commits: the question and its audit entry land together.
    log_action(db, actor_id=user.id, action="offer_clarification.ask", target_type="offer", target_id=offer.id, new_value=clarification.id)
    db.refresh(clarification)
    provider = db.get(User, offer.service_provider_id)
    if provider:
        notify_team(
            db, provider, NotificationType.offer_clarification_requested, organization_id=offer.organization_id,
            link=f"/service-provider/projects/{project_id}/offer", project_title=project.title,
        )
    return clarification_out(db, clarification, owner_side=True)


# ---------- Stage 6.11: the owner side's private evaluation notes ----------


def _note_offer(db: Session, project: Project, offer_id: str | None) -> Offer | None:
    """The offer a note is about: on THIS requirement only, put forward (never a
    draft), not admin-suspended, and not while the tender is sealed (whose
    offers the owner can't yet tell apart). None: the requirement itself."""
    if offer_id is None:
        return None
    offer = db.get(Offer, offer_id)
    if (
        not offer or offer.project_id != project.id or offer.status == OfferStatus.draft or offer.is_suspended
        or is_sealed_and_open(project)
    ):
        raise HTTPException(status_code=404, detail="Offer not found.")
    return offer


def _note_out(db: Session, note: EvaluationNote, user: User) -> EvaluationNoteOut:
    author = db.get(User, note.author_id) if note.author_id else None
    return EvaluationNoteOut(
        id=note.id, project_id=note.project_id, offer_id=note.offer_id, body=note.body,
        author_name=(author.full_name or author.email) if author else None, mine=note.author_id == user.id,
        version=note.version, created_at=note.created_at, updated_at=note.updated_at,
    )


def _own_note(db: Session, project_id: str, note_id: str, user: User, if_match: str | None) -> tuple[Project, EvaluationNote]:
    project = _get_owned_project(project_id, user, db, lock=True)  # an active owner; serialized
    note = db.query(EvaluationNote).filter(EvaluationNote.id == note_id).populate_existing().with_for_update().first()
    if not note or note.project_id != project_id:
        raise HTTPException(status_code=404, detail="Note not found.")
    if note.author_id != user.id:
        raise HTTPException(status_code=403, detail="Only the note's author can change or remove it.")
    if if_match and if_match.strip('"') != str(note.version):
        raise HTTPException(status_code=409, detail="This note was changed somewhere else since you opened it. Reload to see the latest version.")
    return project, note


@router.get("/projects/{project_id}/notes", response_model=list[EvaluationNoteOut])
def list_notes(project_id: str, offer_id: str | None = None, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 6.11: the owner side's notes on this requirement (all of them, or
    those on one offer) -- for its owner side only, in any state."""
    project = _get_owned_project(project_id, user, db)
    query = db.query(EvaluationNote).filter(EvaluationNote.project_id == project_id)
    if offer_id is not None:
        query = query.filter(EvaluationNote.offer_id == _note_offer(db, project, offer_id).id)
    return [_note_out(db, n, user) for n in query.order_by(EvaluationNote.created_at.asc(), EvaluationNote.id)]


@router.post("/projects/{project_id}/notes", response_model=EvaluationNoteOut, status_code=201)
def add_note(project_id: str, payload: EvaluationNoteIn, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status == ProjectStatus.draft:
        raise HTTPException(status_code=400, detail="Notes are for reviewing offers on a published requirement.")
    offer = _note_offer(db, project, payload.offer_id)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Enter a note.")
    if payload.client_token:
        existing = db.query(EvaluationNote).filter(EvaluationNote.author_id == user.id, EvaluationNote.client_token == payload.client_token).first()
        if existing:  # the same submission again (a retry, a double click)
            db.rollback()
            return _note_out(db, existing, user)
    note = EvaluationNote(project_id=project_id, offer_id=offer.id if offer else None, author_id=user.id, body=body, client_token=payload.client_token)
    db.add(note)
    db.flush()
    # log_action commits: the note and its audit entry land together.
    log_action(db, actor_id=user.id, action="evaluation_note.add", target_type="evaluation_note", target_id=note.id, new_value=offer.id if offer else project_id)
    db.refresh(note)
    return _note_out(db, note, user)


@router.put("/projects/{project_id}/notes/{note_id}", response_model=EvaluationNoteOut)
def edit_note(
    project_id: str, note_id: str, payload: EvaluationNoteEdit,
    if_match: str | None = Header(None, alias="If-Match"), user: User = Depends(require_owner), db: Session = Depends(get_db),
):
    _, note = _own_note(db, project_id, note_id, user, if_match)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Enter a note.")
    if body != note.body:
        note.body, note.version, note.updated_at = body, note.version + 1, datetime.utcnow()
        log_action(db, actor_id=user.id, action="evaluation_note.edit", target_type="evaluation_note", target_id=note.id)
    else:
        db.commit()
    db.refresh(note)
    return _note_out(db, note, user)


@router.delete("/projects/{project_id}/notes/{note_id}", status_code=204)
def delete_note(
    project_id: str, note_id: str,
    if_match: str | None = Header(None, alias="If-Match"), user: User = Depends(require_owner), db: Session = Depends(get_db),
):
    _, note = _own_note(db, project_id, note_id, user, if_match)
    db.delete(note)
    log_action(db, actor_id=user.id, action="evaluation_note.delete", target_type="evaluation_note", target_id=note_id)


# ---------- Stage 6.12: the owner side's shortlist ----------


def _shortlist_out(db: Session, offer_id: str, row: OfferShortlist | None) -> ShortlistOut:
    if not row:
        return ShortlistOut(offer_id=offer_id, shortlisted=False)
    who = db.get(User, row.added_by) if row.added_by else None
    return ShortlistOut(
        offer_id=offer_id, shortlisted=True, offer_revision=row.offer_revision, material_revision=row.material_revision,
        added_by_name=(who.full_name or who.email) if who else None, created_at=row.created_at,
    )


def _shortlist_target(project_id: str, offer_id: str, user: User, db: Session) -> tuple[Project, Offer]:
    """An offer the owner's side may shortlist (or take off the shortlist) now:
    their own requirement's live offer, while offers are being evaluated --
    after they close, when neither the offers nor the requirement can change
    any more, and before the outcome. Under the requirement's lock, so it
    can't race the close, the award or another member's change."""
    project = _get_owned_project(project_id, user, db, lock=True)
    offer = _readable_offer(project_id, offer_id, user, db)
    if project.is_suspended:
        raise HTTPException(status_code=400, detail="This requirement has been suspended by an admin.")
    if project.status not in (ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise HTTPException(status_code=400, detail="Offers can be shortlisted only while they are being evaluated: after offers close and before the requirement's outcome.")
    if offer.status != OfferStatus.submitted:
        raise HTTPException(status_code=400, detail="This offer is no longer live.")
    return project, offer


@router.get("/projects/{project_id}/offers/{offer_id}/shortlist", response_model=ShortlistOut)
def get_shortlist(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    offer = _readable_offer(project_id, offer_id, user, db)
    return _shortlist_out(db, offer.id, db.query(OfferShortlist).filter(OfferShortlist.offer_id == offer.id).first())


@router.put("/projects/{project_id}/offers/{offer_id}/shortlist", response_model=ShortlistOut)
def shortlist_offer(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 6.12: put the offer on the shortlist -- promising, NOT an award:
    nothing is decided, sent, changed on the offer, or told to anyone outside
    the owner's side. Several offers may be shortlisted. Repeating it (a
    retry, a second tab) changes nothing."""
    project, offer = _shortlist_target(project_id, offer_id, user, db)
    row = db.query(OfferShortlist).filter(OfferShortlist.offer_id == offer.id).first()
    if row is None:
        row = OfferShortlist(
            project_id=project_id, offer_id=offer.id, offer_revision=offer.revision,
            material_revision=offer.based_on_material_revision, added_by=user.id,
        )
        db.add(row)
        db.flush()
        # log_action commits: the shortlisting and its audit entry land together.
        log_action(db, actor_id=user.id, action="offer.shortlisted", target_type="offer", target_id=offer.id, new_value=f"offer revision {offer.revision}")
        db.refresh(row)
    else:
        db.rollback()  # already shortlisted; release the lock
    return _shortlist_out(db, offer.id, row)


@router.delete("/projects/{project_id}/offers/{offer_id}/shortlist", response_model=ShortlistOut)
def unshortlist_offer(project_id: str, offer_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 6.12: take the offer off the shortlist. Repeating it changes nothing."""
    _, offer = _shortlist_target(project_id, offer_id, user, db)
    row = db.query(OfferShortlist).filter(OfferShortlist.offer_id == offer.id).first()
    if row is not None:
        db.delete(row)
        log_action(db, actor_id=user.id, action="offer.unshortlisted", target_type="offer", target_id=offer.id)
    else:
        db.rollback()
    return _shortlist_out(db, offer.id, None)


@router.get("/projects/{project_id}/offers/{offer_id}/documents/file")
def open_offer_document(
    project_id: str, offer_id: str, label: str, revision: int | None = None, user: User = Depends(require_owner), db: Session = Depends(get_db)
):
    """Stage 6.2: opens one of the offer's documents (as submitted, or as in
    an earlier version) -- authorised again on every click, then a one-minute link."""
    found = offer_file(db, _readable_offer(project_id, offer_id, user, db), label, revision)
    if not found:
        raise HTTPException(status_code=404, detail="Document not found.")
    return open_file(*found)


class AwardRequest(BaseModel):
    # Stage 6.13: awarding an offer made against an earlier version of the
    # requirement (not confirmed by its provider since) needs the owner to say so.
    acknowledge_earlier_version: bool = False


@router.post("/projects/{project_id}/offers/{offer_id}/approve", response_model=ProjectOut)
def approve_offer(
    project_id: str, offer_id: str, payload: AwardRequest | None = None, user: User = Depends(require_owner), db: Session = Depends(get_db)
):
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    # Stage 6.13: an admin-suspended requirement is out of sight until an
    # admin reactivates it -- no decision is taken on it meanwhile.
    if project.is_suspended:
        raise HTTPException(status_code=400, detail="This requirement has been suspended by an admin.")
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
    # Stage 6.13: never silently award an offer priced against an earlier
    # version of the requirement as if it answered the current one.
    if winning_offer.based_on_material_revision < project.material_revision and not (payload and payload.acknowledge_earlier_version):
        raise HTTPException(
            status_code=409,
            detail="This offer was made against an earlier version of the requirement and its provider hasn't confirmed it since. Confirm that you want to award it as it stands.",
        )

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
    award_id = gen_uuid()
    db.add(
        AwardRecord(
            id=award_id,
            project_id=project_id,
            offer_id=winning_offer.id,
            service_provider_id=winning_offer.service_provider_id,
            amount=winning_offer.amount,
            project_revision=project.revision,
            offer_revision=winning_offer.revision,
            awarded_by=user.id,
        )
    )
    db.flush()
    # Stage 7.3: the agreement governing the award comes into being with it,
    # being prepared -- in the same transaction, so there is never an award
    # without its agreement, nor an agreement without its award.
    db.add(Agreement(award_id=award_id, project_id=project_id))
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

    # Best-effort -- the award is committed above; notifying is not part of
    # it. Stage 6.16: a failure to notify never fails the owner's request
    # (the award stands, and every page reads it from the record).
    def tell():
        winner_user = db.get(User, winning_offer.service_provider_id)
        if winner_user:
            notify_service_provider_offer_decision(winner_user.email, project.title, approved=True)
            notify_team(db, winner_user, NotificationType.award_won, link=f"/service-provider/projects/{project_id}/offer", organization_id=winning_offer.organization_id, project_title=project.title)
        for o in other_offers:
            loser_user = db.get(User, o.service_provider_id)
            if loser_user:
                notify_service_provider_offer_decision(loser_user.email, project.title, approved=False)
                notify_team(db, loser_user, NotificationType.award_lost, link=f"/service-provider/projects/{project_id}/offer", organization_id=o.organization_id, project_title=project.title)

    _best_effort(db, tell, f"award notifications for {project_id}")

    db.refresh(project)
    offer_count = db.query(Offer).filter(Offer.project_id == project_id, tendered()).count()
    return ProjectOut(**_project_fields(project), offer_count=offer_count)


# ---------- lifecycle actions (spec §2.12 full tender lifecycle) ----------
# Every transition below is an explicit owner decision; the only automatic
# one is open -> closed/expired, handled lazily by sync_expired_projects.

def _project_response(project: Project, db: Session) -> ProjectOut:
    offer_count = db.query(Offer).filter(Offer.project_id == project.id, tendered()).count()
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
    # Stage 3.18: recorded like every other lifecycle change (log_action commits both together).
    log_action(db, actor_id=user.id, action="project.start_evaluation", target_type="project", target_id=project_id, previous_value="closed", new_value="under_evaluation")
    db.refresh(project)
    return _project_response(project, db)


def _best_effort(db: Session, send, what: str) -> None:
    """Runs notifications after a committed decision; a failure is logged and
    rolled back (whatever of it wasn't committed) -- the decision stands."""
    try:
        send()
    except Exception:  # noqa: BLE001 -- notifying must never undo or fail a decision
        db.rollback()
        logger.exception("Could not send %s", what)


def _notify_bidders(db: Session, project: Project, notification_type: NotificationType, **details) -> None:
    bidders = (
        db.query(Offer.service_provider_id, Offer.organization_id)
        .filter(Offer.project_id == project.id, Offer.status != OfferStatus.withdrawn, tendered())
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


def _notify_watchers(db: Session, project: Project) -> None:
    """A requirement ended while still open for offers: the providers who were
    told about it (or asked about it) but hadn't offered hear it is over,
    rather than it just vanishing from their feed. Bidders are told separately."""
    link = f"/service-provider/projects/{project.id}/offer"
    for person in interested_providers(db, project):
        notify(db, person, NotificationType.requirement_ended, link=link, project_title=project.title)
        notify_provider_requirement_ended(person.email, person.language.value, project_title=project.title, project_id=project.id)
    # A "new opportunity" still waiting to be read no longer is one.
    db.query(Notification).filter(
        Notification.type == NotificationType.new_requirement, Notification.link == link, Notification.is_read.is_(False)
    ).update({Notification.is_read: True}, synchronize_session=False)
    db.commit()


# Stage 3.16: how a requirement ends without a U-Tender award. The status
# says what happened (canceled / no_award / expired); closure_reason says
# why, so outcomes with different meanings stay distinguishable without new
# states. A note, if given, goes to the audit trail only -- it may be
# commercially sensitive, so providers never see it.
CANCEL_REASONS = ("not_needed", "postponed", "other")
NO_AWARD_REASONS = ("no_suitable_offer", "closed_externally")


class ClosureRequest(BaseModel):
    reason: str | None = None
    note: str | None = Field(default=None, max_length=1000)


def _end(db: Session, user: User, project: Project, status: ProjectStatus, reason: str, note: str | None, action: str, kind: NotificationType):
    # Stage 6.14: like the award (6.13), no final outcome is recorded while an
    # admin has the requirement suspended -- it waits for the admin's decision.
    if project.is_suspended:
        raise HTTPException(status_code=400, detail="This requirement has been suspended by an admin.")
    previous = project.status.value
    now = datetime.utcnow().replace(microsecond=0)
    if project.status == ProjectStatus.open:
        project.closed_at = now  # offers stop now
    project.status = status
    project.closure_reason = reason
    project.closure_note = (note or "").strip() or None
    project.paused_at = None
    log_action(
        db, actor_id=user.id, action=action, target_type="project", target_id=project.id,
        previous_value=previous, new_value=f"{status.value}:{reason}", reason=project.closure_note,
    )
    # Stage 6.16: the outcome is committed above; telling people about it is
    # best-effort and never fails the owner's request.
    def tell():
        _notify_bidders(db, project, kind)
        if previous == ProjectStatus.open.value:
            _notify_watchers(db, project)

    _best_effort(db, tell, f"{action} notifications for {project.id}")
    db.refresh(project)
    return _project_response(project, db)


@router.post("/projects/{project_id}/no-award", response_model=ProjectOut)
def mark_no_award(project_id: str, payload: ClosureRequest | None = None, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Offers have closed and none of them is suitable: no award."""
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status not in (ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise HTTPException(status_code=400, detail="Only a closed or under-evaluation project can be marked no-award.")
    note = payload.note if payload else None
    return _end(db, user, project, ProjectStatus.no_award, "no_suitable_offer", note, "project.no_award", NotificationType.tender_no_award)


@router.post("/projects/{project_id}/close-externally", response_model=ProjectOut)
def close_externally(project_id: str, payload: ClosureRequest | None = None, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """The owner will handle the work outside U-Tender. Recorded as ending
    without a U-Tender award -- nobody is awarded, nothing about the outside
    arrangement is asked for or tracked. Possible while offers are open
    (they stop now) or after they close."""
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status not in (ProjectStatus.open, ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise HTTPException(status_code=400, detail="This project can no longer be closed.")
    note = payload.note if payload else None
    return _end(db, user, project, ProjectStatus.no_award, "closed_externally", note, "project.closed_externally", NotificationType.tender_no_award)


@router.post("/projects/{project_id}/cancel", response_model=ProjectOut)
def cancel_project(project_id: str, payload: ClosureRequest | None = None, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """The requirement won't proceed in its current form (no longer needed,
    postponed indefinitely, or another reason). Offers and history stay."""
    sync_expired_projects(db)
    project = _get_owned_project(project_id, user, db, lock=True)
    if project.status == ProjectStatus.draft:
        # A draft was never published: "cancelling" it is discarding it. It
        # must not become a canceled tender, which providers can open.
        db.rollback()
        return discard_draft(project_id, user, db)
    if project.status not in (ProjectStatus.open, ProjectStatus.closed, ProjectStatus.under_evaluation):
        raise HTTPException(status_code=400, detail="This project can no longer be canceled.")
    reason = (payload.reason if payload and payload.reason else "other")
    if reason not in CANCEL_REASONS:
        raise HTTPException(status_code=400, detail="Choose why the requirement is being canceled.")
    return _end(db, user, project, ProjectStatus.canceled, reason, payload.note if payload else None, "project.cancel", NotificationType.tender_cancelled)


# Content that carries over when an ended requirement is started again.
_RESTART_FIELDS = (
    "title", "address", "governorate", "area", "description", "trade", "category_id", "expected_start_date",
    "expected_completion_date", "expected_duration_days", "tender_type", "pricing_basis", "response_requirements",
    "provider_eligibility", "questions_allowed", "commercial_terms", "documents_required", "commercial_conditions",
    "bidder_instructions",
)


class RestartRequest(BaseModel):
    creation_token: str | None = Field(default=None, max_length=64)


@router.post("/projects/{project_id}/restart", response_model=ProjectOut, status_code=201)
def restart_project(project_id: str, payload: RestartRequest | None = None, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """An ended requirement stays ended (canceled, expired, no award), and a
    completed one stays completed (Stage 8.11). When the work comes back --
    postponed, or the same need a year later -- the owner starts a NEW draft
    from its content: description, items, rules, eligibility and current
    documents (fresh copies of the files). Never its state, dates, offers,
    award, transaction, reviews or history.
    Nothing about the old one changes; its offers and history stay with it,
    and the new draft is published (or not) like any other."""
    from app.services.transactions import completed_transaction

    sync_expired_projects(db)
    source = _get_owned_project(project_id, user, db, lock=True)
    # Stage 8.11: also a completed transaction (Stage 7's authoritative
    # completion) -- the same need again, as a new, independent requirement.
    # Never one still open, awarded but unfinished, or a draft.
    ended = source.status in (ProjectStatus.canceled, ProjectStatus.no_award, ProjectStatus.expired)
    if not ended and not (source.status == ProjectStatus.awarded and completed_transaction(db, source.id) is not None):
        raise HTTPException(status_code=400, detail="Only a completed or ended requirement can be used to start a new one.")
    # Stage 8.11: content an admin has suspended isn't copied into a new requirement.
    if source.is_suspended:
        raise HTTPException(status_code=400, detail="This requirement is suspended.")
    token = payload.creation_token if payload and payload.creation_token else None
    if token:
        existing = db.query(Project).filter(Project.owner_id == source.owner_id, Project.creation_token == token).first()
        if existing:
            db.rollback()
            return _project_response(existing, db)
    copy = Project(
        **{f: getattr(source, f) for f in _RESTART_FIELDS},
        owner_id=source.owner_id,
        organization_id=source.organization_id,
        status=ProjectStatus.draft,
        # The old dates have passed: a placeholder the owner sets before publishing.
        bid_deadline=(datetime.utcnow() + timedelta(days=7)).replace(second=0, microsecond=0),
        creation_token=token,
        restarted_from_id=source.id,
    )
    db.add(copy)
    db.flush()
    for item in source.items:
        db.add(ProjectItem(project_id=copy.id, position=item.position, description=item.description, quantity=item.quantity, unit=item.unit, specification=item.specification))
    storage = get_storage()
    for drawing in source.drawings:
        if not drawing.is_current:
            continue
        content = storage.download("project-drawings", drawing.file_path)
        if content is None:
            continue
        path = f"{copy.id}/{drawing.file_path.split('/', 1)[-1]}"
        storage.save("project-drawings", path, content, "application/octet-stream")
        db.add(ProjectDrawing(project_id=copy.id, file_path=path, file_name=drawing.file_name, category=drawing.category, is_required=drawing.is_required, size_bytes=len(content)))
    log_action(db, actor_id=user.id, action="project.restart", target_type="project", target_id=copy.id, previous_value=source.id, new_value="draft")
    db.refresh(copy)
    return _project_response(copy, db)


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


@router.get("/projects/{project_id}/review", response_model=ReviewOut | None)
def get_review(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """The owner side's own review of the provider."""
    project = db.get(Project, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    return review_of(db, project_id, OWNER_TO_PROVIDER)


@router.get("/projects/{project_id}/review/received", response_model=ReceivedReviewOut | None)
def get_received_review(project_id: str, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 8.6: the winning provider's review of this owner side, once
    recorded -- to the requirement's owner side only, as rating, comment and
    date (never ids or the reviewer's account)."""
    project = db.get(Project, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")
    return shown_review_of(db, project_id, PROVIDER_TO_OWNER)  # Stage 8.15: not once an admin has hidden it


@router.post("/projects/{project_id}/review-reports", response_model=ReviewReportOut, status_code=201)
def report_review_content(project_id: str, payload: ReviewReportCreate, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 8.15: the owner side reports the provider's review of it, or the
    provider's response to its own review -- for an admin to look at. Nothing
    changes until an admin decides."""
    project = _get_owned_project(project_id, user, db, lock=True)
    direction = PROVIDER_TO_OWNER if payload.target == "review" else OWNER_TO_PROVIDER
    return report(db, project, direction, payload.target, user, payload.reason, payload.note)


@router.post("/projects/{project_id}/review/received/response", response_model=ReceivedReviewOut)
def respond_to_received_review(project_id: str, payload: ReviewResponseCreate, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 8.9: the owner side's one, final response to the winning
    provider's review of it -- from an active, verified owner account, under
    the requirement's lock, like every other owner action."""
    project = _get_owned_project(project_id, user, db, lock=True)
    return record_response(db, project, PROVIDER_TO_OWNER, user, payload.response)


@router.get("/reputation", response_model=OwnerReputationOut)
def my_reputation(user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 8.8: this owner side's own U-Tender reputation -- its
    organisation's, by current membership; no id is taken from the request."""
    from app.services.reputation import owner_reputation

    return owner_reputation(db, get_owner_profile(user, db).user_id, with_reviews=True)


@router.post("/reviews", response_model=ReviewOut)
def submit_review(payload: ReviewCreate, user: User = Depends(require_owner), db: Session = Depends(get_db)):
    """Stage 8.3: the owner side reviews the provider it awarded, once the
    transaction is completed (8.1) -- once per transaction. Under the
    requirement's lock and from an active, verified owner account like every
    other owner action; the review, the provider's recomputed public rating
    and the audit entry are one transaction (services.reviews)."""
    project = _get_owned_project(payload.project_id, user, db, lock=True)
    return record_review(db, project, OWNER_TO_PROVIDER, user, payload.rating, payload.comment)


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
        closure_reason=p.closure_reason,
        closure_note=p.closure_note,  # owner side only (this router)
        restarted_from_id=p.restarted_from_id,
    )
