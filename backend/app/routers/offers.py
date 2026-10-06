from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_service_provider_profile, require_approved_service_provider, require_marketplace_active_service_provider
from app.models.enums import NotificationType, OfferStatus, ProjectStatus, TenderType
from app.models.offer import Offer, OfferRevision
from app.models.project import Project
from app.models.user import User
from app.schemas.offer import OfferCreate, OfferOut, OfferRevisionOut
from app.services.email import notify_owner_new_offer
from app.services.notify import notify
from app.services.tender_lifecycle import bidding_is_open, lock_project

router = APIRouter(prefix="/projects/{project_id}/offers", tags=["offers"])

# offers.amount is NUMERIC(12,2). The DB rounds to 2 places, so anything at or
# above 9999999999.995 would round past the column's range and fail the insert.
_AMOUNT_LIMIT = Decimal("9999999999.995")


@router.get("/mine", response_model=OfferOut | None)
def my_offer(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    return db.query(Offer).filter(Offer.project_id == project_id, Offer.service_provider_id == user.id).first()


@router.get("/mine/history", response_model=list[OfferRevisionOut])
def my_offer_history(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    offer = db.query(Offer).filter(Offer.project_id == project_id, Offer.service_provider_id == user.id).first()
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
            status=offer.status,
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
    profile = get_service_provider_profile(user, db)

    # Lock the tender row, THEN check it. Checking an unlocked copy let a bid
    # slip in after the owner's close had committed, and two near-simultaneous
    # first bids from one service provider (double-click, retry) both inserted and
    # deadlocked. Under the lock every bid, withdrawal and lifecycle change on
    # this tender is serialized, so the state read below is the state the bid
    # is written against.
    project = lock_project(db, project_id)
    if not project or not bidding_is_open(project):
        raise HTTPException(status_code=400, detail="Bidding on this project is closed.")
    if project.is_suspended:
        raise HTTPException(status_code=400, detail="This project has been suspended and is not accepting offers.")

    if payload.amount <= 0 or payload.amount >= _AMOUNT_LIMIT:
        raise HTTPException(status_code=400, detail="Enter a valid bid amount.")

    # The tender lock above already serializes every writer of this
    # service provider's offer (a plain read is enough). Deliberately NOT
    # SELECT ... FOR UPDATE on the offer: when no row exists yet that takes a
    # next-key/gap lock, and two such locks held at once deadlock on the
    # inserts that follow.
    offer = db.query(Offer).filter(Offer.project_id == project_id, Offer.service_provider_id == user.id).first()
    if offer:
        # upsert on the (project_id, service_provider_id) unique constraint — a
        # service provider revising their bid before the deadline updates the
        # same row rather than creating a duplicate, but the prior values
        # are snapshotted first so nothing is silently lost.
        _snapshot_revision(db, offer)
        offer.amount = payload.amount
        offer.timeline_estimate = payload.timeline_estimate
        offer.message = payload.message
        offer.status = OfferStatus.submitted
        offer.updated_at = datetime.utcnow()
    else:
        offer = Offer(
            project_id=project_id,
            service_provider_id=user.id,
            amount=payload.amount,
            timeline_estimate=payload.timeline_estimate,
            message=payload.message,
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
        notify_owner_new_offer(owner.email, project.title, project_id, profile.company_name, float(payload.amount), sealed=sealed)
        notify(
            db,
            owner,
            NotificationType.bid_submitted,
            link=f"/owner/projects/{project_id}",
            project_title=project.title,
            service_provider_name="A service provider" if sealed else profile.company_name,
        )

    return offer


@router.post("/withdraw", response_model=OfferOut)
def withdraw_offer(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    # Same lock-then-check as submit_offer. Withdrawal is a change to a bid, and
    # bids can't change once bidding has stopped (an awarded bid flipped to
    # "withdrawn" would contradict the permanent AwardRecord; a bid pulled
    # after the deadline would let a bidder walk away from a price the owner is
    # already evaluating).
    project = lock_project(db, project_id)
    offer = db.query(Offer).filter(Offer.project_id == project_id, Offer.service_provider_id == user.id).first()
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
