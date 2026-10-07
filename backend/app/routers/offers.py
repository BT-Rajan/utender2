from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_service_provider_profile, require_approved_service_provider, require_marketplace_active_service_provider
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer, OfferDocument, OfferRevision
from app.models.project import Project
from app.models.user import User
from app.schemas.offer import OfferCreate, OfferDocumentOut, OfferOut, OfferRevisionOut
from app.services.audit import log_action
from app.services.eligibility import assert_eligible
from app.services.email import notify_owner_new_offer
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS, assert_allowed_extension, safe_relative_name, sanitize_path_segment
from app.services.notify import notify, notify_team
from app.services.team import acting_id, acting_profile, can_access, mine, org_of
from app.services.offer_response import OFFER_DOCUMENTS_BUCKET, check_complete, documents_out, priced_total, requirements_for
from app.services.storage import get_storage
from app.services.tender_lifecycle import bidding_is_open, lock_project

router = APIRouter(prefix="/projects/{project_id}/offers", tags=["offers"])

# offers.amount is NUMERIC(15,3) (KWD has 3 decimals). Totals are capped well
# inside the column's range; more than 3 decimals is refused by the schema.
_AMOUNT_LIMIT = Decimal("10000000000")


@router.get("/mine", response_model=OfferOut | None)
def my_offer(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    return _with_documents(db, offer) if offer else None


def _with_documents(db: Session, offer: Offer) -> OfferOut:
    out = OfferOut.model_validate(offer)
    out.documents = documents_out(db, offer.project_id, offer.organization_id, offer.service_provider_id)
    return out


# ---------- Stage 3.8: documents a provider submits with their response ----------


@router.get("/documents", response_model=list[OfferDocumentOut])
def my_offer_documents(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """The provider's own response attachments (there may be some before the
    offer itself is first submitted)."""
    return documents_out(db, project_id, org_of(db, user.id), acting_id(db, user))


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
    else:
        db.add(OfferDocument(project_id=project_id, service_provider_id=acting_id(db, user), organization_id=org_of(db, user.id), label=label, file_path=path, file_name=safe_relative_name(file.filename)))
    db.commit()
    if replaced:
        try:
            storage.delete(OFFER_DOCUMENTS_BUCKET, [replaced])
        except Exception:
            pass
    return documents_out(db, project_id, org_of(db, user.id), acting_id(db, user))


@router.delete("/documents/{document_id}", response_model=list[OfferDocumentOut])
def remove_offer_document(
    project_id: str, document_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)
):
    project = lock_project(db, project_id)
    doc = db.get(OfferDocument, document_id)
    if not project or not doc or doc.project_id != project_id or not can_access(db, user, doc.organization_id, doc.service_provider_id):
        raise HTTPException(status_code=404, detail="Document not found.")
    if not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project has closed.")
    path = doc.file_path
    db.delete(doc)
    db.commit()
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
    return (
        db.query(OfferRevision)
        .filter(OfferRevision.offer_id == offer.id)
        .order_by(OfferRevision.revision_number.asc())
        .all()
    )


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
            message=offer.message,
            item_prices=offer.item_prices,
            assumptions=offer.assumptions,
            status=offer.status,
            based_on_material_revision=offer.based_on_material_revision,
        )
    )
    offer.revision += 1


@router.post("", response_model=OfferOut)
def submit_offer(
    project_id: str,
    payload: OfferCreate,
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
    if amount is None or amount <= 0 or amount >= _AMOUNT_LIMIT:
        raise HTTPException(status_code=400, detail="Enter a valid bid amount.")
    declarations = check_complete(db, project, org_of(db, user.id), acting_id(db, user), payload)

    # The tender lock above already serializes every writer of this
    # service provider's offer (a plain read is enough). Deliberately NOT
    # SELECT ... FOR UPDATE on the offer: when no row exists yet that takes a
    # next-key/gap lock, and two such locks held at once deadlock on the
    # inserts that follow.
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if offer:
        # upsert on the (project_id, service_provider_id) unique constraint — a
        # service provider revising their bid before the deadline updates the
        # same row rather than creating a duplicate, but the prior values
        # are snapshotted first so nothing is silently lost.
        _snapshot_revision(db, offer)
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
        )
        db.add(offer)
    # The tender type is a material term of the tender — once at least one
    # bid exists, the owner can no longer switch sealed <-> owner-visible
    # out from under bidders (spec §19-21, D-001). Idempotent: stays locked
    # on every subsequent revision too.
    if not project.tender_type_locked:
        project.tender_type_locked = True
    db.commit()
    db.refresh(offer)

    sealed = project.tender_type == TenderType.sealed and project.status == ProjectStatus.open
    owner = db.get(User, project.owner_id)
    if owner:
        notify_owner_new_offer(owner.email, project.title, project_id, profile.company_name, float(amount), sealed=sealed)
        notify_team(
            db,
            owner,
            NotificationType.bid_submitted,
            organization_id=project.organization_id,
            link=f"/owner/projects/{project_id}",
            project_title=project.title,
            service_provider_name="A service provider" if sealed else profile.company_name,
        )

    return _with_documents(db, offer)


@router.post("/confirm", response_model=OfferOut)
def confirm_offer(project_id: str, user: User = Depends(require_marketplace_active_service_provider), db: Session = Depends(get_db)):
    """Stage 3.15: after a material change to the requirement, the provider
    confirms their offer still stands as submitted -- its price and content
    unchanged -- against the requirement as it now is. (To change anything,
    they revise the offer instead.) The same rules as revising apply: only
    while bidding is open, and only for an eligible provider."""
    project = lock_project(db, project_id)
    offer = db.query(Offer).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first()
    if not project or not offer or offer.status != OfferStatus.submitted:
        raise HTTPException(status_code=404, detail="No offer to confirm.")
    if not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project is closed.")
    assert_eligible(db, project, acting_profile(db, user))
    if offer.based_on_material_revision >= project.material_revision:
        raise HTTPException(status_code=400, detail="Your offer is already up to date with the requirement.")
    previous = offer.based_on_material_revision
    # Stage 3.17: the trail keeps that it was first made against the earlier version.
    _snapshot_revision(db, offer)
    offer.based_on_material_revision = project.material_revision
    offer.updated_at = datetime.utcnow()
    db.commit()
    log_action(
        db, actor_id=user.id, action="offer.confirmed", target_type="offer", target_id=offer.id,
        previous_value=f"material revision {previous}", new_value=f"material revision {project.material_revision}",
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
    if not project or not offer:
        raise HTTPException(status_code=404, detail="No offer to withdraw.")
    if offer.status == OfferStatus.withdrawn:
        raise HTTPException(status_code=400, detail="This offer has already been withdrawn.")
    if not bidding_is_open(project):
        raise HTTPException(
            status_code=400, detail="Bidding on this project has closed, so this offer can no longer be withdrawn."
        )
    _snapshot_revision(db, offer)
    offer.status = OfferStatus.withdrawn
    offer.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(offer)
    return offer
