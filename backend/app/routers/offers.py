from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.i18n_server import translate
from app.deps import get_service_provider_profile, require_approved_service_provider, require_marketplace_active_service_provider, require_service_provider
from app.models.clarification import Clarification
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer, OfferDocument, OfferRevision
from app.models.project import Project
from app.models.user import User
from app.schemas.offer import OfferAssumptionsDraft, OfferCommercialDraft, OfferDeclarationsDraft, OfferDraftSave, OfferPreviewOut, OfferReadiness, PreviewRequirement, OfferCreate, OfferTechnicalDraft, OfferTimingDraft, OfferDocumentOut, OfferOut, OfferRevisionOut
from app.schemas.clarification import OfferClarificationAnswer, OfferClarificationOut
from app.services.audit import log_action
from app.services.offer_clarifications import clarification_out, offer_clarifications
from app.services.offer_clarifications import closed_reason as clarification_closed_reason
from app.services.eligibility import assert_eligible
from app.services.email import notify_owner_new_offer
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS, assert_allowed_extension, safe_relative_name, sanitize_path_segment
from app.services.notify import notify, notify_team
from app.services.team import acting_id, acting_profile, can_access, mine, org_of
from app.services.offer_response import (
    AMOUNT_LIMIT, OFFER_DOCUMENTS_BUCKET, _side_documents, offer_file, open_file, check_commitment, history_out, check_complete, documents_out, draft_pricing, priced_total, readiness, requirements_for,
    timing_conflicts,
)
from app.services.storage import get_storage
from app.services.tender_lifecycle import bidding_is_open, lock_project, sync_expired_projects
from app.services.tender_rules import START_PASSED_DETAIL, answers_since, offer_valid_until, start_date_passed, validity_lapsed

router = APIRouter(prefix="/projects/{project_id}/offers", tags=["offers"])


@router.get("/mine", response_model=OfferOut | None)
def my_offer(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """This provider's side's one offer on the requirement, in whatever state --
    including the draft Participate started (Stage 5.2). Found by who is
    asking (their stakeholder), never by an id from the request."""
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    return _with_documents(db, offer) if offer else None


def _with_documents(db: Session, offer: Offer) -> OfferOut:
    out = OfferOut.model_validate(offer)
    out.documents = documents_out(db, offer.project_id, offer.organization_id, offer.service_provider_id)
    project = db.get(Project, offer.project_id)
    out.timing_conflicts = timing_conflicts(project, offer) if project else []  # Stage 5.5
    if project:
        _validity(db, project, offer, out)
    out.withdrawals_left = max(0, MAX_WITHDRAWALS - (offer.withdrawal_count or 0))
    return out


# Batch B: withdrawing and putting an offer forward again is allowed, but not
# without end -- the second withdrawal is final.
MAX_WITHDRAWALS = 2


def _validity(db: Session, project: Project, offer: Offer, out: OfferOut) -> OfferOut:
    if offer.status == OfferStatus.submitted:
        out.valid_until = offer_valid_until(project, offer)
        out.validity_lapsed = validity_lapsed(project, offer)
        out.answers_since = answers_since(db, project, offer)
    return out


# ---------- Stage 5.3/5.4: saving the offer draft (price, technical response) ----------


def _draft_for_edit(db: Session, user: User, project_id: str, if_match: str | None) -> tuple[Project, Offer]:
    """Stage 5.3/5.4: the provider's own side's offer draft, locked for one
    save. Judged under the requirement's lock, like every offer change: only
    while bidding is open, for an eligible provider, on their side's draft
    (found by who is asking, never an id from the request), against the
    requirement version they have seen, and from a page showing the latest
    draft (If-Match: draft_version)."""
    project = lock_project(db, project_id)
    if project and project.is_suspended:
        raise HTTPException(status_code=400, detail="This project has been suspended and is not accepting offers.")
    if not project or not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project is closed.")
    assert_eligible(db, project, acting_profile(db, user))
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Start preparing your offer first.")
    if offer.status != OfferStatus.draft:
        raise HTTPException(status_code=409, detail="Your offer has already been submitted. Change it by updating your offer.")
    if offer.based_on_material_revision < project.material_revision:
        raise HTTPException(status_code=409, detail="The requirement changed after you started this offer. Review the current requirement first.")
    if if_match is not None and if_match.strip('"') != str(offer.draft_version):
        raise HTTPException(
            status_code=409,
            detail="Your offer draft was changed somewhere else (another tab, device or team member) since you opened it. Reload to see the latest, then make your change again.",
        )
    return project, offer


def _saved(db: Session, user: User, offer: Offer) -> OfferOut:
    offer.draft_version += 1
    offer.updated_at, offer.updated_by = datetime.utcnow(), user.id
    db.commit()
    db.refresh(offer)
    return _with_documents(db, offer)


@router.put("/draft", response_model=OfferOut)
def save_draft(
    project_id: str,
    payload: OfferDraftSave,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 5.10: save the whole offer form on the provider's draft in one
    step -- price, technical response, assumptions, declarations and timing
    -- without submitting it. Every part is checked by the same rules as its
    own save (5.3-5.8) before anything is written, so a save either lands
    whole, once, with one new draft_version, or not at all: no half-saved
    draft after a failure, a refresh or a retry. Same gates as every draft
    save, including If-Match against a stale page. Documents are attached
    separately (5.6) and are untouched."""
    project, offer = _draft_for_edit(db, user, project_id, if_match)
    amount, item_prices = draft_pricing(project, payload.amount, payload.item_prices)
    check_commitment(project, payload.proposed_start_date, payload.proposed_completion_date, payload.proposed_duration_days)
    declared = requirements_for(project).declarations
    if set(payload.accepted_declarations) - set(declared):
        raise HTTPException(status_code=400, detail="That declaration isn't part of this requirement.")
    offer.amount, offer.item_prices = amount, item_prices
    offer.message = (payload.message or "").strip() or None
    offer.assumptions = (payload.assumptions or "").strip() or None
    offer.declarations_accepted = [d for d in declared if d in set(payload.accepted_declarations)] or None
    offer.proposed_start_date = payload.proposed_start_date
    offer.proposed_completion_date = payload.proposed_completion_date
    offer.proposed_duration_days = payload.proposed_duration_days
    offer.timeline_estimate = (payload.timeline_estimate or "").strip() or None
    return _saved(db, user, offer)


@router.put("/draft/commercial", response_model=OfferOut)
def save_commercial_draft(
    project_id: str,
    payload: OfferCommercialDraft,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    """Save the price -- one total, or a rate per item -- on this provider's
    offer draft (Stage 5.2), without submitting it. The requirement's
    pricing basis, items, quantities and currency are read from the
    requirement, never from the request. Nothing else on the draft changes."""
    project, offer = _draft_for_edit(db, user, project_id, if_match)
    offer.amount, offer.item_prices = draft_pricing(project, payload.amount, payload.item_prices)
    return _saved(db, user, offer)


@router.put("/draft/technical", response_model=OfferOut)
def save_technical_draft(
    project_id: str,
    payload: OfferTechnicalDraft,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 5.4: save the technical response -- the requirement's "technical
    approach / method" (Stage 3.8) -- on this provider's offer draft,
    without submitting it. Only that text changes: the price, the
    requirement and everything else stay as they are. Whether the
    requirement makes it mandatory is checked when the offer is submitted."""
    _, offer = _draft_for_edit(db, user, project_id, if_match)
    offer.message = (payload.message or "").strip() or None
    return _saved(db, user, offer)


@router.put("/draft/assumptions", response_model=OfferOut)
def save_assumptions_draft(
    project_id: str,
    payload: OfferAssumptionsDraft,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 5.7: save the provider's assumptions, exclusions,
    qualifications and offer clarifications on their offer draft, without
    submitting it -- kept exactly as written (never interpreted or
    accepted here) for the owner to weigh once the offer is submitted.
    Only that text changes."""
    _, offer = _draft_for_edit(db, user, project_id, if_match)
    offer.assumptions = (payload.assumptions or "").strip() or None
    return _saved(db, user, offer)


@router.put("/draft/declarations", response_model=OfferOut)
def save_declarations_draft(
    project_id: str,
    payload: OfferDeclarationsDraft,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 5.8: save which of the requirement's declarations the provider
    accepts on their draft -- only the requirement's own, as worded -- so
    the quality gate can say whether they're all accepted. Only that field
    changes."""
    project, offer = _draft_for_edit(db, user, project_id, if_match)
    declared = requirements_for(project).declarations
    if set(payload.accepted_declarations) - set(declared):
        raise HTTPException(status_code=400, detail="That declaration isn't part of this requirement.")
    offer.declarations_accepted = [d for d in declared if d in set(payload.accepted_declarations)] or None
    return _saved(db, user, offer)


@router.get("/draft/check", response_model=OfferReadiness)
def check_offer(project_id: str, user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    """Stage 5.8: the quality gate -- can this provider's saved offer be
    submitted now, and if not, everything still to do, by part of the
    offer? Judged on the server, against the requirement as it is now (state,
    deadline, version), the provider's standing now and the requirement's own
    response rules. Read-only: it grants nothing -- submission makes its own
    checks again, under the requirement's lock. Only the provider's own
    side's offer; a requirement they can't see is not found."""
    sync_expired_projects(db)
    project = db.get(Project, project_id)
    if not project or project.status == ProjectStatus.draft:
        raise HTTPException(status_code=404, detail="Project not found.")
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    issues = readiness(db, project, acting_profile(db, user), offer)
    for issue in issues:  # in the viewer's language, like every server message
        issue.message = translate(issue.message)
    return OfferReadiness(ready=not issues, issues=issues)


def preview_requirement(db: Session, project: Project) -> PreviewRequirement:
    """Stage 5.9 (and 6.4, for the owner): enough of the requirement, as it is
    now, to read an offer against -- its items, the declarations and
    documents it asked for, its current version."""
    from app.models.project_amendment import ProjectAmendment
    from app.schemas.project import ProjectItemOut

    latest = (
        db.query(ProjectAmendment.amendment_number)
        .filter(ProjectAmendment.project_id == project.id)
        .order_by(ProjectAmendment.amendment_number.desc())
        .first()
    )
    reqs = requirements_for(project)
    return PreviewRequirement(
        id=project.id, title=project.title, trade=project.trade, governorate=project.governorate, area=project.area,
        description=project.description, pricing_basis=project.pricing_basis.value, currency=get_settings().marketplace_currency,
        tender_type=project.tender_type.value, bid_deadline=project.bid_deadline,
        expected_start_date=project.expected_start_date, expected_completion_date=project.expected_completion_date,
        expected_duration_days=project.expected_duration_days, material_revision=project.material_revision,
        amendment_number=latest[0] if latest else None,
        items=[ProjectItemOut.model_validate(i) for i in sorted(project.items, key=lambda i: i.position)],
        declarations=list(reqs.declarations), requested_documents=[{"name": d.name, "required": d.required} for d in reqs.documents],
        approach=reqs.approach, completion_period=reqs.completion_period, status=project.status.value,
    )


@router.get("/draft/preview", response_model=OfferPreviewOut)
def preview_offer(project_id: str, user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    """Stage 5.9: what this provider's side would submit, exactly as stored --
    price, technical response, timing, documents, assumptions, declarations
    -- read fresh from the one offer row on every request (no preview copy),
    beside the requirement as it is now and the quality gate's verdict.
    Only the provider's own side's offer, on a requirement they may open;
    anything else is not found. Read-only: it submits, seals and locks
    nothing."""
    from app.routers.projects import _can_view_project

    sync_expired_projects(db)
    project = db.get(Project, project_id)
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first() if project else None
    if not project or project.status == ProjectStatus.draft or not offer or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="No offer to preview.")
    profile = acting_profile(db, user)
    issues = readiness(db, project, profile, offer)
    for issue in issues:
        issue.message = translate(issue.message)
    requirement = preview_requirement(db, project)
    return OfferPreviewOut(
        requirement=requirement, provider_name=profile.company_name if profile else None, offer=_with_documents(db, offer),
        readiness=OfferReadiness(ready=not issues, issues=issues),
        on_current_version=offer.based_on_material_revision >= project.material_revision,
    )


@router.put("/draft/timing", response_model=OfferOut)
def save_timing_draft(
    project_id: str,
    payload: OfferTimingDraft,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 5.5: save when the provider commits to start and finish -- a
    start date, a completion date or a duration, and the free-text
    completion period -- on their offer draft, without submitting it.
    Checked to make sense on its own (dates real and in order, no work
    before offers close, a duration of 1 day to 10 years); where it differs
    from the owner's expected timing it is kept as entered and flagged
    (timing_conflicts). Only these fields change; the requirement's own
    timing is never touched."""
    project, offer = _draft_for_edit(db, user, project_id, if_match)
    check_commitment(project, payload.proposed_start_date, payload.proposed_completion_date, payload.proposed_duration_days)
    offer.proposed_start_date = payload.proposed_start_date
    offer.proposed_completion_date = payload.proposed_completion_date
    offer.proposed_duration_days = payload.proposed_duration_days
    offer.timeline_estimate = (payload.timeline_estimate or "").strip() or None
    return _saved(db, user, offer)



# ---------- Stage 3.8: documents a provider submits with their response ----------


@router.get("/documents", response_model=list[OfferDocumentOut])
def my_offer_documents(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """The provider's own response attachments (there may be some before the
    offer itself is first submitted)."""
    return documents_out(db, project_id, org_of(db, user.id), acting_id(db, user))


def _offer_for_documents(db: Session, user: User, project: Project) -> Offer:
    """Stage 5.6: the side's offer the documents belong to -- its draft, or
    the offer it became. Attaching a document is preparing an offer, so with
    none yet (an older page) the draft is started here, as Participate does;
    the caller has already checked everything Participate checks. A draft
    started before a material change takes no new document until the
    current requirement has been reviewed."""
    from app.routers.projects import ensure_draft, record_decision

    offer = db.query(Offer).filter(Offer.project_id == project.id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if offer is None:
        record_decision(db, user, project)
        ensure_draft(db, user, project)
        db.flush()
        offer = db.query(Offer).filter(Offer.project_id == project.id, mine(db, user, Offer, Offer.service_provider_id)).first()
    elif offer.status == OfferStatus.draft and offer.based_on_material_revision < project.material_revision:
        raise HTTPException(status_code=409, detail="The requirement changed after you started this offer. Review the current requirement first.")
    return offer


@router.post("/documents", response_model=list[OfferDocumentOut])
async def upload_offer_document(
    project_id: str,
    label: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    project = lock_project(db, project_id)
    if not project or not bidding_is_open(project) or project.is_suspended:
        raise HTTPException(status_code=400, detail="Bidding on this project is closed.")
    assert_eligible(db, project, acting_profile(db, user))
    requested = {d.name for d in requirements_for(project).documents}
    if label not in requested:
        raise HTTPException(status_code=400, detail="This requirement doesn't ask for that document.")
    assert_allowed_extension(file.filename, ALLOWED_DRAWING_EXTENSIONS - {"zip"})
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="No file provided.")
    offer = _offer_for_documents(db, user, project)

    storage = get_storage()
    path = f"{project_id}/{user.id}/{int(datetime.utcnow().timestamp() * 1000)}-{sanitize_path_segment(file.filename)}"
    storage.save(OFFER_DOCUMENTS_BUCKET, path, content, file.content_type or "application/octet-stream")
    existing = (
        db.query(OfferDocument)
        .filter(OfferDocument.project_id == project_id, mine(db, user, OfferDocument, OfferDocument.service_provider_id), OfferDocument.label == label)
        .first()
    )
    replaced = existing.file_path if existing else None
    if existing:
        existing.file_path, existing.file_name = path, safe_relative_name(file.filename)
        existing.uploaded_at = datetime.utcnow()
        existing.offer_id, existing.material_revision, existing.uploaded_by = offer.id, project.material_revision, user.id
    else:
        db.add(OfferDocument(
            project_id=project_id, service_provider_id=acting_id(db, user), organization_id=org_of(db, user.id), label=label,
            file_path=path, file_name=safe_relative_name(file.filename),
            offer_id=offer.id, material_revision=project.material_revision, uploaded_by=user.id,
        ))
    try:
        db.commit()
    except Exception:  # never leave a stored file no record points to
        db.rollback()
        try:
            storage.delete(OFFER_DOCUMENTS_BUCKET, [path])
        except Exception:
            pass
        raise
    # Stage 5.13: a file that went with a submitted version stays on record
    # (that version's history refers to it); only a draft's is discarded.
    if replaced and offer.submitted_at is None:
        try:
            storage.delete(OFFER_DOCUMENTS_BUCKET, [replaced])
        except Exception:
            pass
    return documents_out(db, project_id, org_of(db, user.id), acting_id(db, user))


@router.delete("/documents/{document_id}", response_model=list[OfferDocumentOut])
def remove_offer_document(
    project_id: str, document_id: str, user: User = Depends(require_marketplace_active_service_provider), db: Session = Depends(get_db)
):
    # Stage 5.6: the same gates as attaching one -- a change to the offer.
    project = lock_project(db, project_id)
    doc = db.get(OfferDocument, document_id)
    if not project or not doc or doc.project_id != project_id or not can_access(db, user, doc.organization_id, doc.service_provider_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    if not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project has closed.")
    assert_eligible(db, project, acting_profile(db, user))
    offer = _offer_for_documents(db, user, project)
    path = doc.file_path
    db.delete(doc)
    db.commit()
    if offer.submitted_at is None:  # Stage 5.13: a submitted version's file stays on record
        try:
            get_storage().delete(OFFER_DOCUMENTS_BUCKET, [path])
        except Exception:
            pass
    return documents_out(db, project_id, org_of(db, user.id), acting_id(db, user))


@router.get("/mine/history", response_model=list[OfferRevisionOut])
def my_offer_history(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if not offer:
        return []
    return history_out(db, db.query(OfferRevision).filter(OfferRevision.offer_id == offer.id).order_by(OfferRevision.revision_number.asc()), "provider", project_id)


@router.get("/mine/documents/file")
def open_my_offer_document(
    project_id: str, label: str, revision: int | None = None, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)
):
    """Stage 6.2: opens a document of the side's own offer as submitted (or
    as in an earlier version) -- authorised on every click, then a one-minute link."""
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    found = offer_file(db, offer, label, revision) if offer else None
    if not found:
        raise HTTPException(status_code=404, detail="Document not found.")
    return open_file(*found)


@router.get("/mine/clarifications", response_model=list[OfferClarificationOut])
def my_offer_clarifications(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """Stage 6.10: what the owner has asked about this side's own offer (found
    by who is asking, never an id from the request), with any answers."""
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    return offer_clarifications(db, offer, owner_side=False) if offer else []


@router.post("/mine/clarifications/{clarification_id}/answer", response_model=OfferClarificationOut)
def answer_offer_clarification(
    project_id: str, clarification_id: str, payload: OfferClarificationAnswer,
    user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db),
):
    """Stage 6.10: answer the owner's clarification of this side's own offer,
    during evaluation. Text beside the offer: the price, response, timing,
    documents and assumptions stay exactly as submitted. Answered once."""
    project = lock_project(db, project_id)  # serialized with the requirement's outcome and the offer's state
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first() if project else None
    clarification = (
        db.query(Clarification).filter(Clarification.id == clarification_id).populate_existing().with_for_update().first() if offer else None
    )
    if not clarification or clarification.offer_id != offer.id:
        raise HTTPException(status_code=404, detail="Clarification not found.")
    if clarification.answer is not None:
        raise HTTPException(status_code=400, detail="This clarification has already been answered.")
    reason = clarification_closed_reason(project, offer)
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Enter an answer.")
    clarification.answer, clarification.answered_at, clarification.answered_by = answer, datetime.utcnow(), user.id
    # log_action commits: the answer and its audit entry land together.
    log_action(db, actor_id=user.id, action="offer_clarification.answer", target_type="offer", target_id=offer.id, new_value=clarification.id)
    db.refresh(clarification)
    owner = db.get(User, project.owner_id)
    if owner:
        notify_team(
            db, owner, NotificationType.offer_clarification_answered, organization_id=project.organization_id,
            link=f"/owner/projects/{project_id}/offers/{offer.id}", project_title=project.title,
        )
    return clarification_out(db, clarification, owner_side=False)


@router.get("/documents/{document_id}/file")
def open_my_document(project_id: str, document_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """Stage 6.2: opens one of the side's current attachments -- found among
    the caller's own side's documents only, authorised on every click."""
    d = _side_documents(db, project_id, org_of(db, user.id), acting_id(db, user)).filter(OfferDocument.id == document_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Document not found.")
    return open_file(d.file_path, d.file_name)


def _snapshot_revision(db: Session, offer: Offer) -> None:
    """Freezes the CURRENT (pre-edit) state of this offer into an
    OfferRevision row before it gets overwritten, then bumps the counter.
    Called for every edit and every withdrawal — the row in `offers` is
    always the latest state, `offer_revisions` is the append-only trail of
    everything it used to be (spec §29, D-009)."""
    db.add(
        OfferRevision(
            offer_id=offer.id,
            revision_number=offer.revision,
            amount=offer.amount,
            timeline_estimate=offer.timeline_estimate,
            proposed_start_date=offer.proposed_start_date,
            proposed_completion_date=offer.proposed_completion_date,
            proposed_duration_days=offer.proposed_duration_days,
            message=offer.message,
            item_prices=offer.item_prices,
            assumptions=offer.assumptions,
            status=offer.status,
            based_on_material_revision=offer.based_on_material_revision,
            # Stage 5.13: the version's declarations and documents as submitted,
            # and when and by whom it was put forward.
            declarations_accepted=offer.declarations_accepted,
            documents=offer.submitted_documents,
            submitted_at=offer.updated_at,
            submitted_by=offer.updated_by,
        )
    )
    offer.revision += 1


@router.post("", response_model=OfferOut)
def submit_offer(
    project_id: str,
    payload: OfferCreate,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    profile = acting_profile(db, user)

    # Lock the tender row, THEN check it. Checking an unlocked copy let a bid
    # slip in after the owner's close had committed, and two near-simultaneous
    # first bids from one service provider (double-click, retry) both inserted and
    # deadlocked. Under the lock every bid, withdrawal and lifecycle change on
    # this tender is serialized, so the state read below is the state the bid
    # is written against.
    project = lock_project(db, project_id)
    if project and project.is_suspended:
        raise HTTPException(status_code=400, detail="This project has been suspended and is not accepting offers.")
    if not project or not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project is closed.")
    # Stage 3.9: the requirement's own eligibility rules, checked at the
    # moment of every submission and revision.
    assert_eligible(db, project, profile)

    # Stage 3.8: the response must match what the requirement asks for --
    # its pricing basis and its response rules.
    amount, item_prices = priced_total(project, payload)
    if amount is None or amount <= 0 or amount >= AMOUNT_LIMIT:
        raise HTTPException(status_code=400, detail="Enter a valid bid amount.")
    declarations = check_complete(db, project, org_of(db, user.id), acting_id(db, user), payload)

    # The tender lock above already serializes every writer of this
    # service provider's offer (a plain read is enough). Deliberately NOT
    # SELECT ... FOR UPDATE on the offer: when no row exists yet that takes a
    # next-key/gap lock, and two such locks held at once deadlock on the
    # inserts that follow.
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    # Stage 5.3: a draft started before a material change is made into an
    # offer only once the provider has reviewed the current requirement
    # (Participate again) -- the same rule as saving the draft, so the
    # browser can't skip it by submitting directly.
    if offer and offer.status == OfferStatus.draft and offer.based_on_material_revision < project.material_revision:
        raise HTTPException(status_code=409, detail="The requirement changed after you started this offer. Review the current requirement first.")
    # Stage 5.8: the start/completion commitment must be valid now (the
    # deadline may have moved since it was saved) -- the same rule the quality
    # gate applies; a submission can't skip it. Stage 5.13: as revised, when
    # the revision changes it.
    timing_fields = ("proposed_start_date", "proposed_completion_date", "proposed_duration_days")
    revised_timing = {f: getattr(payload, f) for f in timing_fields if f in payload.model_fields_set}
    commitment = {f: revised_timing.get(f, getattr(offer, f) if offer else None) for f in timing_fields}
    check_commitment(project, commitment["proposed_start_date"], commitment["proposed_completion_date"], commitment["proposed_duration_days"])
    if offer and offer.status == OfferStatus.withdrawn and (offer.withdrawal_count or 0) >= MAX_WITHDRAWALS:
        raise HTTPException(status_code=400, detail="This offer has been withdrawn twice, so it can't be put forward again on this requirement.")
    first = offer is None or offer.status == OfferStatus.draft  # Stage 5.11: put forward for the first time
    # Stage 5.13: revising a submitted (or withdrawn) offer from a page showing
    # an earlier revision -- another tab, a colleague, a retried request -- is
    # refused rather than overwriting the newer one (If-Match: revision).
    if offer and not first and if_match is not None and if_match.strip('"') != str(offer.revision):
        raise HTTPException(
            status_code=409,
            detail="Your offer was changed somewhere else (another tab, device or team member) since you opened it. Reload to see the latest, then make your change again.",
        )
    if offer:
        # upsert on the (project_id, service_provider_id) unique constraint — a
        # service provider revising their bid before the deadline updates the
        # same row rather than creating a duplicate, but the prior values
        # are snapshotted first so nothing is silently lost. Stage 5.2: a
        # draft (started by Participate) becomes the offer itself -- it was
        # never put forward, so there is no earlier submission to keep.
        if offer.status != OfferStatus.draft:
            _snapshot_revision(db, offer)
        offer.updated_by = user.id
        offer.amount = amount
        offer.timeline_estimate = payload.timeline_estimate
        offer.message = payload.message
        offer.item_prices = item_prices
        offer.assumptions = payload.assumptions
        offer.declarations_accepted = declarations
        offer.based_on_material_revision = project.material_revision  # made against the requirement as it now stands
        offer.status = OfferStatus.submitted
        offer.updated_at = datetime.utcnow()
    else:
        offer = Offer(
            project_id=project_id,
            service_provider_id=acting_id(db, user),  # the stakeholder: the organization, for a member
            organization_id=org_of(db, user.id),
            amount=amount,
            timeline_estimate=payload.timeline_estimate,
            message=payload.message,
            item_prices=item_prices,
            assumptions=payload.assumptions,
            declarations_accepted=declarations,
            based_on_material_revision=project.material_revision,
            status=OfferStatus.submitted,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(offer)
    for field, value in revised_timing.items():
        setattr(offer, field, value)
    return _put_forward(db, user, project, offer, profile, first)


def _put_forward(db: Session, user: User, project: Project, offer: Offer, profile, first: bool) -> OfferOut:
    """Stage 5.11: the one way an offer becomes (or, revised, stays) a formal
    submitted offer -- for a direct submission and for submitting the stored
    draft alike. The caller holds the requirement's lock and has written the
    offer's content on the row (not yet committed). Here, under that same
    lock: the Stage 5.8 quality gate runs on exactly what will be committed
    (state, server deadline, version, standing, eligibility and the
    requirement's own rules), so nothing incomplete, late or ineligible is
    ever committed -- on any failure the whole change is rolled back and the
    stored draft is as it was. Then one commit, and only after it the
    owner's notifications."""
    offer.status = OfferStatus.submitted
    issues = readiness(db, project, profile, offer)
    if issues:
        db.rollback()
        raise HTTPException(status_code=400, detail=" ".join(dict.fromkeys(i.message for i in issues)))
    now = datetime.utcnow()
    if first or offer.submitted_at is None:
        offer.submitted_at = now
    # Stage 5.13: the documents that go with this version, as they stand now.
    db.flush()
    offer.submitted_documents = [
        {"label": d.label, "file_name": d.file_name, "file_path": d.file_path}
        for d in _side_documents(db, offer.project_id, offer.organization_id, offer.service_provider_id).order_by(OfferDocument.label.asc())
    ] or None
    offer.updated_at, offer.updated_by = now, user.id
    # The tender type is a material term of the tender — once at least one
    # bid exists, the owner can no longer switch sealed <-> owner-visible
    # out from under bidders (spec §19-21, D-001). Idempotent: stays locked
    # on every subsequent revision too.
    if not project.tender_type_locked:
        project.tender_type_locked = True
    # Stage 4.9: offering is deciding to take part (recorded once, at the
    # version the offer is made against), in the same commit.
    from app.routers.projects import record_decision

    record_decision(db, user, project)
    # Stage 9.7: on the audit trail in the same commit -- who put it forward,
    # which revision, against which version of the requirement (never the price).
    log_action(db, actor_id=user.id, action="offer.submit" if first else "offer.revise", target_type="offer", target_id=offer.id,
               new_value=f"revision {offer.revision} on requirement v{offer.based_on_material_revision} ({project.id})")
    db.refresh(offer)

    sealed = project.tender_type == TenderType.sealed and project.status == ProjectStatus.open
    owner = db.get(User, project.owner_id)
    if owner:
        if first:
            notify_owner_new_offer(owner.email, project.title, project.id, profile.company_name, float(offer.amount), sealed=sealed)
        notify_team(
            db,
            owner,
            NotificationType.bid_submitted if first else NotificationType.bid_revised,  # Stage 5.11: a revision is not a new offer
            organization_id=project.organization_id,
            link=f"/owner/projects/{project.id}",
            project_title=project.title,
            service_provider_name="A service provider" if sealed else profile.company_name,
        )

    return _with_documents(db, offer)


@router.post("/draft/submit", response_model=OfferOut)
def submit_draft(
    project_id: str,
    if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(require_marketplace_active_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 5.11: submit the stored draft -- exactly what was saved and
    previewed (5.9), nothing from the request but If-Match: the
    draft_version the provider reviewed, so a colleague's or another tab's
    later change is never submitted unseen. Under the requirement's lock
    (the one every close, pause, suspension, amendment and the deadline
    sync takes), so one authoritative outcome wins any race. Re-checks
    everything at this moment through the same gate as every submission;
    a draft that has already been submitted, by a repeat request, another
    tab or a colleague, is not submitted again."""
    project = lock_project(db, project_id)
    if project and project.is_suspended:
        raise HTTPException(status_code=400, detail="This project has been suspended and is not accepting offers.")
    if not project or not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project is closed.")
    profile = acting_profile(db, user)
    assert_eligible(db, project, profile)
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Start preparing your offer first.")
    if offer.status != OfferStatus.draft:
        raise HTTPException(status_code=409, detail="Your offer has already been submitted. Change it by updating your offer.")
    if offer.based_on_material_revision < project.material_revision:
        raise HTTPException(status_code=409, detail="The requirement changed after you started this offer. Review the current requirement first.")
    if if_match is not None and if_match.strip('"') != str(offer.draft_version):
        raise HTTPException(
            status_code=409,
            detail="Your offer draft was changed somewhere else (another tab, device or team member) since you opened it. Reload to see the latest, then make your change again.",
        )
    return _put_forward(db, user, project, offer, profile, first=True)


@router.post("/confirm", response_model=OfferOut)
def confirm_offer(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """Stage 3.15: after a material change to the requirement, the provider
    confirms their offer still stands as submitted -- its price and content
    unchanged -- against the requirement as it now is. (To change anything,
    they revise the offer instead.) While bidding is open the same rules as
    revising apply: an eligible provider with active access. After the close
    (Batch B) the owner can't award until the provider confirms, so that needs
    only an account in good standing -- a lapsed subscription must not leave
    the award, and so the other side's work, stuck."""
    project = lock_project(db, project_id)
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if not project or not offer or offer.status != OfferStatus.submitted:
        raise HTTPException(status_code=404, detail="No offer to confirm.")
    if project.status in (ProjectStatus.closed, ProjectStatus.under_evaluation) and not project.is_suspended:
        return _confirm_after_close(db, user, project, offer)
    if not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project is closed.")
    profile = acting_profile(db, user)
    if not profile or not profile.is_verified_active:
        raise HTTPException(status_code=403, detail="payment_required")  # same code and gate as require_marketplace_active_service_provider
    assert_eligible(db, project, profile)
    if offer.based_on_material_revision >= project.material_revision:
        raise HTTPException(status_code=400, detail="Your offer is already up to date with the requirement.")
    # Stage 5.15: confirming re-states the offer against the requirement as it
    # now is -- its start/completion commitment must still be valid now (an
    # amendment may have moved the deadline past it); if not, it is revised,
    # not confirmed.
    check_commitment(project, offer.proposed_start_date, offer.proposed_completion_date, offer.proposed_duration_days)
    previous = offer.based_on_material_revision
    # Stage 3.17: the trail keeps that it was first made against the earlier version.
    _snapshot_revision(db, offer)
    offer.based_on_material_revision = project.material_revision
    offer.updated_at, offer.updated_by = datetime.utcnow(), user.id
    db.commit()
    log_action(
        db, actor_id=user.id, action="offer.confirmed", target_type="offer", target_id=offer.id,
        previous_value=f"material revision {previous}", new_value=f"material revision {project.material_revision}",
    )
    db.refresh(offer)
    return _with_documents(db, offer)


def _confirm_after_close(db: Session, user: User, project: Project, offer: Offer) -> OfferOut:
    """Batch B: once offers have closed, the owner can award only an offer its
    provider stands by -- made against the requirement as it now is, and
    within its validity period. Confirming re-states it, unchanged, against
    the current version and restarts its validity from now. Only the
    provider confirms; the owner can ask (request-confirmation)."""
    if start_date_passed(offer):  # Batch D: confirming would re-open an offer the owner can't award
        raise HTTPException(status_code=400, detail=START_PASSED_DETAIL)
    if offer.based_on_material_revision >= project.material_revision and not validity_lapsed(project, offer) and offer_valid_until(project, offer) is None:
        raise HTTPException(status_code=400, detail="Your offer is already up to date with the requirement.")
    previous = offer.based_on_material_revision
    if previous < project.material_revision:
        _snapshot_revision(db, offer)
        offer.based_on_material_revision = project.material_revision
    now = datetime.utcnow().replace(microsecond=0)
    offer.validity_confirmed_at = now
    offer.updated_at, offer.updated_by = now, user.id
    log_action(
        db, actor_id=user.id, action="offer.confirmed", target_type="offer", target_id=offer.id,
        previous_value=f"material revision {previous}", new_value=f"material revision {project.material_revision}; stands from {now.isoformat()}Z",
    )
    db.refresh(offer)
    return _with_documents(db, offer)


@router.post("/withdraw", response_model=OfferOut)
def withdraw_offer(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    # Same lock-then-check as submit_offer. Withdrawal is a change to a bid, and
    # bids can't change once bidding has stopped (an awarded bid flipped to
    # "withdrawn" would contradict the permanent AwardRecord; a bid pulled
    # after the deadline would let a bidder walk away from a price the owner is
    # already evaluating).
    project = lock_project(db, project_id)
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if not project or not offer or offer.status == OfferStatus.draft:  # Stage 5.2: nothing was put forward
        raise HTTPException(status_code=404, detail="No offer to withdraw.")
    if offer.status == OfferStatus.withdrawn:
        raise HTTPException(status_code=400, detail="This offer has already been withdrawn.")
    if offer.status != OfferStatus.submitted:
        raise HTTPException(status_code=400, detail="This offer has already been decided, so it can no longer be withdrawn.")
    # Batch B: after the close an offer is held only for its validity period;
    # once that has run out (and the provider hasn't confirmed it since), the
    # provider is free to withdraw it.
    lapsed_after_close = project.status in (ProjectStatus.closed, ProjectStatus.under_evaluation) and validity_lapsed(project, offer)
    if not bidding_is_open(project) and not lapsed_after_close:
        raise HTTPException(
            status_code=400, detail="Bidding on this project has closed, so this offer can no longer be withdrawn."
        )
    _snapshot_revision(db, offer)
    offer.withdrawal_count = (offer.withdrawal_count or 0) + 1
    offer.status = OfferStatus.withdrawn
    offer.updated_at, offer.updated_by = datetime.utcnow(), user.id
    # Stage 9.7: withdrawn, by whom, in the same commit.
    log_action(db, actor_id=user.id, action="offer.withdraw", target_type="offer", target_id=offer.id,
               previous_value="submitted", new_value=f"withdrawn ({project.id})")
    db.refresh(offer)
    # The owner's team is told an offer they may be weighing is gone -- after
    # the commit, and without the provider's name while the tender is sealed.
    owner = db.get(User, project.owner_id)
    if owner:
        sealed = project.tender_type == TenderType.sealed and project.status == ProjectStatus.open
        profile = acting_profile(db, user)
        notify_team(
            db, owner, NotificationType.bid_withdrawn, organization_id=project.organization_id, link=f"/owner/projects/{project.id}",
            project_title=project.title, service_provider_name="A service provider" if sealed or not profile else profile.company_name,
        )
    return _with_documents(db, offer)  # Stage 5.14: the same shape as every other offer response
