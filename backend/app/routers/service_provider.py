from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_service_provider_profile, get_current_user, require_approved_service_provider, require_service_provider
from app.models.service_provider import ServiceProviderProfile
from app.models.document import DocumentRequirement
from app.models.enums import DocumentStatus, ProjectStatus, UserRole
from app.models.offer import Offer
from app.models.project import Project, ProjectItem
from app.models.user import User
from app.schemas.service_provider import ServiceProviderProfileOut, MyBidOut, SubmitForReview
from app.schemas.document import ServiceProviderDocumentOut, DocumentRequirementOut
from app.schemas.project import FeedPage, ProjectOut
from app.schemas.category import ProviderServices
from app.services.categories import clean_services
from app.services.eligibility import ineligibility_reasons
from app.services.team import acting_profile, mine
from app.services.file_security import ALLOWED_DOCUMENT_EXTENSIONS, assert_allowed_extension, sanitize_path_segment
from app.services.locations import clean_governorate
from app.services.stakeholder import require_established
from app.services.verification import (
    applicable_requirements,
    assert_can_upload,
    assert_editable,
    assert_ready_to_submit,
    checklist,
    document_out_fields,
    mark_submitted,
    profile_state_fields,
)
from app.services.storage import get_storage
from app.services.tender_lifecycle import sync_expired_projects

router = APIRouter(prefix="/service-provider", tags=["service_provider"])


# Any authenticated service provider can read the active checklist — mirrors the
# original "requirements_read" RLS policy (using (true)) rather than the
# admin-only write endpoints under /admin/requirements.
@router.get("/requirements", response_model=list[DocumentRequirementOut])
def active_requirements(user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    """The admin-configured requirements that apply to this account's
    stakeholder type right now."""
    cp = get_service_provider_profile(user, db)
    return applicable_requirements(db, UserRole.service_provider, cp.stakeholder_type)


def _eligibility_fields(db: Session, project: Project, profile) -> dict:
    # Stage 3.9 / 4.1: the feed holds only what this provider may respond to
    # (or already bid on, whose conditions may since have lapsed: then why).
    reasons = ineligibility_reasons(db, project, profile)
    return {"eligible": not reasons, "ineligible_reasons": reasons}


FEED_PAGE = 20
FEED_PAGE_MAX = 50
_FEED_BATCH = 100
SUMMARY_CHARS = 240


@router.get("/feed", response_model=FeedPage)
def feed(
    trade: str | None = None,
    governorate: str | None = None,
    search: str | None = None,
    sort: str = "deadline",  # "deadline" (closing soonest, default) | "newest"
    offset: int = Query(0, ge=0),
    limit: int = Query(FEED_PAGE, ge=1, le=FEED_PAGE_MAX),
    user: User = Depends(require_approved_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 4.1: the opportunities this provider can actually take part in --
    published, open, not suspended, before their deadline, and (Stage 3.9)
    whose conditions they meet; or that they already bid on. A page at a
    time: the database is read in bounded batches, in a stable order, only as
    far as the page needs."""
    # The feed itself requires verification approval (mirrors middleware.ts's
    # serviceProviderGatedPaths) — subscription is a separate, softer gate applied
    # only to drawings and offer submission below, not to seeing the feed.
    sync_expired_projects(db)
    now = datetime.utcnow()
    query = db.query(Project).filter(
        Project.status == ProjectStatus.open,
        Project.is_suspended.is_(False),
        Project.bid_deadline > now,  # authoritative even for a row the sync skipped
    )

    if trade and trade.strip():
        query = query.filter(Project.trade.ilike(f"%{trade.strip()}%"))
    if governorate and governorate.strip():
        query = query.filter(Project.governorate == clean_governorate(governorate))
    if search and search.strip():
        # Never matched against the exact address: a search must not let a
        # listing-level viewer probe for a specific property.
        term = f"%{search.strip()}%"
        query = query.filter(or_(Project.title.ilike(term), Project.area.ilike(term), Project.description.ilike(term)))

    # "Newest" means newest on the marketplace: by publication (Stage 3.14),
    # not by when the owner started the draft. The id breaks ties so pages
    # never overlap or skip.
    newest = func.coalesce(Project.published_at, Project.created_at).desc()
    query = query.order_by(newest, Project.id) if sort == "newest" else query.order_by(Project.bid_deadline.asc(), Project.id)

    my_offers = {o.project_id: o.status.value for o in db.query(Offer).filter(mine(db, user, Offer, Offer.service_provider_id)).all()}
    profile = acting_profile(db, user)

    # Walk the matches in order, keeping those this provider may respond to,
    # until the page (plus one, to know whether there is more) is filled.
    page: list[Project] = []
    seen_available, hidden, scanned, more = 0, 0, 0, False
    while not more:
        batch = query.offset(scanned).limit(_FEED_BATCH).all()
        scanned += len(batch)
        for p in batch:
            if p.id not in my_offers and ineligibility_reasons(db, p, profile):
                hidden += 1
                continue
            seen_available += 1
            if seen_available <= offset:
                continue
            if len(page) < limit:
                page.append(p)
            else:
                more = True
                break
        if len(batch) < _FEED_BATCH:
            break

    ids = [p.id for p in page]
    offer_counts = dict(db.query(Offer.project_id, func.count(Offer.id)).filter(Offer.project_id.in_(ids)).group_by(Offer.project_id).all()) if ids else {}
    item_counts = dict(db.query(ProjectItem.project_id, func.count(ProjectItem.id)).filter(ProjectItem.project_id.in_(ids)).group_by(ProjectItem.project_id).all()) if ids else {}
    full_access = bool(profile and profile.is_verified_active)

    out = []
    for p in page:
        out.append(
            ProjectOut(
                id=p.id,
                owner_id=p.owner_id,
                title=p.title,
                # Listing level: where (governorate/area) and what (title,
                # trade, the opening of the scope) only. The exact address and
                # the full scope -- which holds site and access notes -- are
                # on the requirement itself.
                address=None,
                governorate=p.governorate,
                area=p.area,
                description=None,
                summary=_summary(p.description) if full_access else None,
                trade=p.trade,
                category_id=p.category_id,
                paused_at=p.paused_at,
                pause_reason=p.pause_reason,
                bid_deadline=p.bid_deadline,
                published_at=p.published_at,
                expected_start_date=p.expected_start_date,
                expected_completion_date=p.expected_completion_date,
                expected_duration_days=p.expected_duration_days,
                status=p.status,
                tender_type=p.tender_type,
                tender_type_locked=p.tender_type_locked,
                pricing_basis=p.pricing_basis.value,
                item_count=item_counts.get(p.id, 0),
                created_at=p.created_at,
                offer_count=offer_counts.get(p.id, 0),
                my_offer_status=my_offers.get(p.id),
                **_eligibility_fields(db, p, profile),
            )
        )
    return FeedPage(
        items=out,
        next_offset=offset + len(out) if more else None,
        # Only free to know when everything was scanned: an empty first page.
        hidden_ineligible=hidden if not out and offset == 0 else None,
    )


def _summary(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_CHARS else text[: SUMMARY_CHARS].rsplit(" ", 1)[0] + "…"


@router.get("/feed/trades", response_model=list[str])
def feed_trades(user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """Distinct trades among currently open projects, for populating the
    feed's filter control — only values actually worth filtering by."""
    sync_expired_projects(db)
    rows = (
        db.query(Project.trade)
        .filter(Project.status == ProjectStatus.open, Project.is_suspended.is_(False), Project.bid_deadline > datetime.utcnow(), Project.trade.isnot(None))
        .distinct()
        .order_by(Project.trade.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]


@router.get("/my-bids", response_model=list[MyBidOut])
def my_bids(user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    """Every offer this service provider has ever placed, across all projects —
    the dashboard's single source for 'active bids' / 'won' counts and the
    My Bids list. Requires only the role, not verification/payment: a
    service provider should always be able to see what they've already bid on
    even if their access later lapses."""
    sync_expired_projects(db)
    rows = (
        db.query(Offer, Project)
        .join(Project, Offer.project_id == Project.id)
        .filter(mine(db, user, Offer, Offer.service_provider_id))
        .order_by(Offer.updated_at.desc())
        .all()
    )
    return [
        MyBidOut(
            project_id=p.id,
            project_title=p.title,
            project_address=p.address,
            project_status=p.status,
            closure_reason=p.closure_reason,
            project_suspended=p.is_suspended,
            bid_deadline=p.bid_deadline,
            offer_id=o.id,
            amount=o.amount,
            offer_status=o.status,
            revision=o.revision,
            updated_at=o.updated_at,
        )
        for o, p in rows
    ]


@router.get("/profile", response_model=ServiceProviderProfileOut)
def profile(user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    cp = get_service_provider_profile(user, db)
    return ServiceProviderProfileOut(**_profile_fields(cp), email=user.email)


@router.put("/services", response_model=ServiceProviderProfileOut)
def set_services(payload: ProviderServices, user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    """Stage 3.9: what this provider offers and where, in the platform's
    structured terms. A declaration, editable at any time -- not part of
    verification. Requirements that match on category or governorate use it."""
    cp = get_service_provider_profile(user, db)
    cp.service_categories, cp.service_governorates = clean_services(db, payload.categories, payload.governorates)
    db.commit()
    db.refresh(cp)
    return ServiceProviderProfileOut(**_profile_fields(cp), email=user.email)


@router.get("/documents", response_model=list[ServiceProviderDocumentOut])
def list_documents(user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    """This account's checklist: one row per applicable requirement."""
    rows = checklist(db, get_service_provider_profile(user, db))
    db.commit()
    return [ServiceProviderDocumentOut(**document_out_fields(d, r)) for r, d in rows]


@router.post("/documents/{requirement_id}/upload", response_model=ServiceProviderDocumentOut)
async def upload_document(
    requirement_id: str,
    file: UploadFile = File(...),
    user: User = Depends(require_service_provider),
    db: Session = Depends(get_db),
):
    cp = get_service_provider_profile(user, db)
    entry = next(((r, d) for r, d in checklist(db, cp) if r.id == requirement_id), None)
    if not entry:
        assert_editable(cp)
        raise HTTPException(status_code=404, detail="Document requirement not found for this service provider.")
    requirement, doc = entry
    # Stage 3.9: a verified provider can add an optional qualification at any
    # time; everything else only while verification is being completed.
    assert_can_upload(cp, requirement)

    assert_allowed_extension(file.filename, ALLOWED_DOCUMENT_EXTENSIONS)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="No file provided.")

    safe_name = sanitize_path_segment(file.filename)
    path = f"{user.id}/{requirement_id}/{int(datetime.utcnow().timestamp() * 1000)}-{safe_name}"
    get_storage().save("service-provider-documents", path, content, file.content_type or "application/octet-stream")

    doc.file_path = path
    doc.status = DocumentStatus.pending
    doc.submitted_at = datetime.utcnow()
    doc.admin_note = None  # clear any prior correction note on re-upload
    doc.expires_on = None  # a fresh submission needs a fresh review before any expiry applies
    db.commit()
    db.refresh(doc)
    return ServiceProviderDocumentOut(**document_out_fields(doc, db.get(DocumentRequirement, requirement_id)))


@router.post("/submit-for-review", response_model=ServiceProviderProfileOut)
def submit_for_review(payload: SubmitForReview, user: User = Depends(require_service_provider), db: Session = Depends(get_db)):
    cp = get_service_provider_profile(user, db)
    require_established(cp)
    assert_editable(cp)
    assert_ready_to_submit(db, cp)
    cp.company_name = payload.company_name
    cp.license_number = payload.license_number
    mark_submitted(cp)
    db.commit()
    db.refresh(cp)
    return ServiceProviderProfileOut(**_profile_fields(cp), email=user.email)


def _profile_fields(cp: ServiceProviderProfile) -> dict:
    return dict(
        user_id=cp.user_id,
        company_name=cp.company_name,
        license_number=cp.license_number,
        primary_trade=cp.primary_trade,
        service_area=cp.service_area,
        service_categories=cp.service_categories or [],
        service_governorates=cp.service_governorates or [],
        verification_status=cp.verification_status,
        is_suspended=cp.is_suspended,
        avg_rating=cp.avg_rating,
        review_count=cp.review_count,
        subscription_status=cp.subscription_status,
        subscription_current_period_end=cp.subscription_current_period_end,
        payment_override_active=cp.payment_override_active,
        marketplace_status=cp.marketplace_status,
        created_at=cp.created_at,
        **profile_state_fields(cp),
    )
