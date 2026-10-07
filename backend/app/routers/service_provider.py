from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_, case, false, func, not_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_service_provider_profile, get_current_user, require_approved_service_provider, require_service_provider
from app.models.service_provider import ServiceProviderProfile
from app.models.document import DocumentRequirement
from app.models.enums import DocumentStatus, ProjectStatus, UserRole
from app.models.offer import Offer
from app.models.project import Project, ProjectDrawing, ProjectItem
from app.models.saved_opportunity import SavedOpportunity
from app.models.user import User
from app.schemas.service_provider import ServiceProviderProfileOut, MyBidOut, SubmitForReview
from app.schemas.document import ServiceProviderDocumentOut, DocumentRequirementOut
from app.schemas.project import FeedPage, ProjectOut
from app.schemas.category import ProviderServices
from app.services.categories import clean_services
from app.services.eligibility import availability, feed_condition, ineligibility_reasons, rules_out
from app.services.search_text import arabic_root, expand, normalize, search_words
from app.models.category import ServiceCategory
from app.services.team import acting_id, acting_profile, mine, org_of, team_ids
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
SUMMARY_CHARS = 240


@router.get("/feed", response_model=FeedPage)
def feed(
    trade: str | None = None,
    governorate: str | None = None,
    search: str | None = Query(None, max_length=200),
    # "deadline" (closing soonest, default) | "deadline_latest" | "newest"
    # (published) | "relevance" (with a search: best text match first)
    sort: Literal["deadline", "deadline_latest", "newest", "relevance"] = "deadline",
    # Stage 4.2: the platform's type of work; the provider's own declared
    # services/areas; time left to respond; only those accepting offers now.
    category_id: str | None = None,
    my_services: bool = False,
    my_areas: bool = False,
    min_days: int = Query(0, ge=0, le=365),
    accepting: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(FEED_PAGE, ge=1, le=FEED_PAGE_MAX),
    user: User = Depends(require_approved_service_provider),
    db: Session = Depends(get_db),
):
    """Stage 4.1: the opportunities this provider can actually take part in --
    published, open, not suspended, before their deadline, and (Stage 3.9)
    whose conditions they meet; or that they already bid on. One bounded
    page at a time, every condition in the database query."""
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
    base = query

    profile = acting_profile(db, user)
    full_access = bool(profile and profile.is_verified_active)

    # Every condition below is part of the database query, applied before
    # the page is cut -- and only ever narrows what this provider may see.
    if trade and trade.strip():
        query = query.filter(Project.search_trade.like(f"%{_like(normalize(trade))}%", escape="/"))
    if category_id:
        query = query.filter(Project.category_id == category_id)
    if governorate and governorate.strip():
        query = query.filter(Project.governorate == clean_governorate(governorate))
    if my_services or my_areas:
        # What the provider (an organization: any of its members) declared.
        team = db.query(ServiceProviderProfile).filter(ServiceProviderProfile.user_id.in_(team_ids(db, user.id))).all()
        if my_services:
            offered = sorted({c for p in team for c in (p.service_categories or [])})
            # Filed under one of those types of work -- or, filed with a
            # free-text type of work, naming one of them.
            names = [normalize(c.name) for c in db.query(ServiceCategory).filter(ServiceCategory.id.in_(offered))] if offered else []
            query = query.filter(or_(
                Project.category_id.in_(offered),
                and_(Project.category_id.is_(None), or_(false(), *(Project.search_trade.like(f"%{_like(n)}%", escape="/") for n in names if n))),
            ))
        if my_areas:
            served = sorted({g for p in team for g in (p.service_governorates or [])})
            if served:  # none declared = all of Kuwait
                query = query.filter(or_(Project.governorate.in_(served), Project.governorate.is_(None)))
    if min_days:
        query = query.filter(Project.bid_deadline >= now + timedelta(days=min_days))
    if accepting:
        query = query.filter(Project.paused_at.is_(None))
    words = search_words(search or "")
    relevance = None
    if words:
        # Every word (normalized: Arabic letter variants, diacritics, digits,
        # case; lightly stemmed) must appear somewhere the provider can see:
        # title, area/governorate, type of work -- and the scope only for
        # providers who can read it. Never the exact address: a search must
        # not let a listing-level viewer probe for a specific property.
        weighted = [(Project.search_title, 3), (Project.search_trade, 2), (Project.search_place, 1)]
        roots = [Project.search_roots]
        if full_access:
            weighted.append((Project.search_scope, 1))
            roots.append(Project.search_scope_roots)
        # Each word also matches its synonyms and, for a likely typo, the
        # nearest words open opportunities actually use (search_text.expand).
        vocabulary: set[str] = set()
        if any(len(w) >= 5 for w in words):
            for row in base.with_entities(Project.search_title, Project.search_trade, Project.search_place):
                vocabulary.update(w for text in row if text for w in text.split() if len(w) >= 4)
        score = []
        for word in words:
            # The word as typed counts double; its synonyms, typo corrections
            # and (Arabic) root count once -- so they widen the search but
            # rank below exact matches.
            terms = expand(word, vocabulary)
            exact = [_contains(col, word) for col, _ in weighted]
            found = [or_(*(_contains(col, t) for t in terms)) for col, _ in weighted]
            root = arabic_root(word)
            by_root = [col.like(f"% {_like(root)} %", escape="/") for col in roots] if root else []
            query = query.filter(or_(*found, *by_root))
            score += [case((hit, 2 * weight), (any_, weight), else_=0) for hit, any_, (_, weight) in zip(exact, found, weighted)]
            score += [case((hit, 1), else_=0) for hit in by_root]
        relevance = sum(score[1:], score[0])

    # "Newest" means newest on the marketplace: by publication (Stage 3.14),
    # not by when the owner started the draft. "Relevance" (with a search):
    # where the words were found -- title, then type of work, then place and
    # scope -- closing soonest among equals. The id breaks ties so pages
    # never overlap or skip.
    if sort == "relevance" and relevance is not None:
        query = query.order_by(relevance.desc(), Project.bid_deadline.asc(), Project.id)
    elif sort == "newest":
        query = query.order_by(func.coalesce(Project.published_at, Project.created_at).desc(), Project.id)
    elif sort == "deadline_latest":
        query = query.order_by(Project.bid_deadline.desc(), Project.id)
    else:
        query = query.order_by(Project.bid_deadline.asc(), Project.id)
    narrowed = bool(trade or category_id or governorate or my_services or my_areas or min_days or accepting or words)

    my_offers = {o.project_id: o.status.value for o in db.query(Offer).filter(mine(db, user, Offer, Offer.service_provider_id)).all()}
    # Stage 3.9 eligibility, in the query (services.eligibility.feed_condition):
    # what this provider may respond to, or already bid on.
    available = or_(feed_condition(db, profile), Project.id.in_(list(my_offers)))
    rows = query.filter(available).offset(offset).limit(limit + 1).all()
    page, more = rows[:limit], len(rows) > limit
    hidden = 0
    if not page and offset == 0 and not narrowed:
        hidden = query.filter(not_(available)).count()

    saved_ids = _saved_ids(db, user)
    out = _cards(db, page, profile, my_offers, full_access, saved_ids)
    return FeedPage(
        items=out,
        next_offset=offset + len(out) if more else None,
        # Only free to know when everything was scanned: an empty first page.
        # Never for a narrowed query, which would tell how many restricted
        # requirements match a given search.
        hidden_ineligible=hidden if not out and offset == 0 and not narrowed else None,
    )


def _cards(db: Session, page: list[Project], profile, my_offers: dict, full_access: bool, saved_ids: set[str]) -> list[ProjectOut]:
    """The opportunity summary (Stage 4.3) for a list of requirements -- the
    feed's and the saved list's one representation."""
    ids = [p.id for p in page]
    offer_counts = dict(db.query(Offer.project_id, func.count(Offer.id)).filter(Offer.project_id.in_(ids)).group_by(Offer.project_id).all()) if ids else {}
    item_counts = dict(db.query(ProjectItem.project_id, func.count(ProjectItem.id)).filter(ProjectItem.project_id.in_(ids)).group_by(ProjectItem.project_id).all()) if ids else {}
    document_counts = dict(
        db.query(ProjectDrawing.project_id, func.count(ProjectDrawing.id))
        .filter(ProjectDrawing.project_id.in_(ids), ProjectDrawing.is_current.is_(True))
        .group_by(ProjectDrawing.project_id).all()
    ) if ids else {}
    return [
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
            closure_reason=p.closure_reason,
            tender_type=p.tender_type,
            tender_type_locked=p.tender_type_locked,
            pricing_basis=p.pricing_basis.value,
            item_count=item_counts.get(p.id, 0),
            document_count=document_counts.get(p.id, 0),
            conditions=rules_out(db, p) if (p.elig_org_only or p.elig_quals or p.elig_match_category or p.elig_match_governorate) else None,
            created_at=p.created_at,
            offer_count=offer_counts.get(p.id, 0),
            my_offer_status=my_offers.get(p.id),
            saved=p.id in saved_ids,
            **_eligibility_fields(db, p, profile),
        )
        for p in page
    ]


def _saved_ids(db: Session, user: User) -> set[str]:
    return {pid for (pid,) in db.query(SavedOpportunity.project_id).filter(mine(db, user, SavedOpportunity, SavedOpportunity.service_provider_id))}


def _contains(column, term: str):
    """The term inside the column's normalized text. A very short term (1-3
    letters, e.g. "ac") must start a word, so it doesn't match inside others."""
    if len(term) <= 3:
        return or_(column.like(f"{_like(term)}%", escape="/"), column.like(f"% {_like(term)}%", escape="/"))
    return column.like(f"%{_like(term)}%", escape="/")


def _like(text: str) -> str:
    """Literal text inside a LIKE pattern (a typed % or _ matches itself)."""
    return text.replace("/", "//").replace("%", "/%").replace("_", "/_")


def _summary(text: str | None) -> str | None:
    if not text:
        return None
    text = " ".join(text.split())
    return text if len(text) <= SUMMARY_CHARS else text[: SUMMARY_CHARS].rsplit(" ", 1)[0] + "…"


# ---------- Stage 4.8: saved opportunities ----------

class SavedState(BaseModel):
    project_id: str
    saved: bool


@router.put("/saved/{project_id}", response_model=SavedState)
def save_opportunity(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """Mark an opportunity to come back to. Only one this provider can
    discover now -- open, not hidden, before its deadline, and theirs to
    respond to (or already bid on) -- so saving never reaches past the feed.
    Saving again changes nothing."""
    sync_expired_projects(db)
    project = db.get(Project, project_id)
    profile = acting_profile(db, user)
    has_bid = project is not None and db.query(Offer.id).filter(Offer.project_id == project_id, mine(db, user, Offer, Offer.service_provider_id)).first() is not None
    if (
        not project or project.status != ProjectStatus.open or project.is_suspended or project.bid_deadline <= datetime.utcnow()
        or not (has_bid or not ineligibility_reasons(db, project, profile))
    ):
        raise HTTPException(status_code=404, detail="Project not found.")
    if project_id not in _saved_ids(db, user):
        db.add(SavedOpportunity(project_id=project_id, service_provider_id=acting_id(db, user), organization_id=org_of(db, user.id), saved_by=user.id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # saved at the same moment by another request: it's saved
    return SavedState(project_id=project_id, saved=True)


@router.delete("/saved/{project_id}", response_model=SavedState)
def unsave_opportunity(project_id: str, user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """Take it off the list -- whatever has become of the requirement since.
    Removing what isn't there changes nothing."""
    db.query(SavedOpportunity).filter(
        SavedOpportunity.project_id == project_id, mine(db, user, SavedOpportunity, SavedOpportunity.service_provider_id)
    ).delete(synchronize_session=False)
    db.commit()
    return SavedState(project_id=project_id, saved=False)


@router.get("/saved", response_model=list[ProjectOut])
def saved_opportunities(user: User = Depends(require_approved_service_provider), db: Session = Depends(get_db)):
    """The saved list, each as the feed's card with where it stands NOW
    (availability): still open first, closing soonest; then those that have
    ended. A saved item never makes anything look available that isn't, and
    shows no more than the provider may see: once a requirement has ended,
    the listing only (its scope only for a provider who took part); hidden by
    U-Tender, nothing about it."""
    sync_expired_projects(db)
    rows = (
        db.query(Project)
        .join(SavedOpportunity, SavedOpportunity.project_id == Project.id)
        .filter(mine(db, user, SavedOpportunity, SavedOpportunity.service_provider_id))
        .limit(500)
        .all()
    )
    profile = acting_profile(db, user)
    my_offers = {o.project_id: o.status.value for o in db.query(Offer).filter(mine(db, user, Offer, Offer.service_provider_id)).all()}
    full_access = bool(profile and profile.is_verified_active)
    state = {p.id: availability(p) for p in rows}
    rank = {"open": 0, "paused": 0, "ended": 1, "unavailable": 2}
    rows.sort(key=lambda p: (rank[state[p.id]], p.bid_deadline if rank[state[p.id]] == 0 else -p.bid_deadline.timestamp(), p.id))
    cards = _cards(db, rows, profile, my_offers, full_access, {p.id for p in rows})
    for card in cards:
        card.availability = state[card.id]
        if card.availability == "unavailable":
            # Hidden by U-Tender: that it's unavailable, and nothing else.
            card.title, card.area, card.governorate, card.trade, card.summary, card.conditions = "", None, None, None, None, None
            card.pause_reason, card.offer_count, card.item_count, card.document_count = None, 0, None, None
        elif card.availability == "ended" and card.id not in my_offers:
            card.summary, card.pause_reason = None, None
    return cards


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
