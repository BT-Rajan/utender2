"""Stage 3.8: what a provider's response must contain, checked against the
requirement's response rules (Project.response_requirements) and its pricing
basis (Stage 3.4). Used by the existing offer submission -- there is one offer
system; this only decides whether a submission is complete."""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.enums import PricingBasis
from app.models.offer import OfferDocument
from app.models.project import Project
from app.schemas.offer import OfferCreate, OfferDocumentOut
from app.schemas.project import ResponseRequirements
from app.services.storage import get_storage

OFFER_DOCUMENTS_BUCKET = "offer-documents"
_FILS = Decimal("0.001")
_LINK_SECONDS = 60 * 60 * 24


def requirements_for(project: Project) -> ResponseRequirements:
    return ResponseRequirements(**(project.response_requirements or {}))


# offers.amount is NUMERIC(15,3) (KWD has 3 decimals). Totals are capped well
# inside the column's range; more than 3 decimals is refused by the schema.
AMOUNT_LIMIT = Decimal("10000000000")


def _lines(project: Project, rates: dict) -> list[dict]:
    """Line total = rate x quantity (or the rate itself for an item with no
    quantity), for each item priced, in the requirement's order."""
    lines = []
    for item in sorted(project.items, key=lambda i: i.position):
        if item.id in rates:
            rate = rates[item.id]
            line_total = (rate * item.quantity if item.quantity is not None else rate).quantize(_FILS, ROUND_HALF_UP)
            lines.append({"item_id": item.id, "rate": str(rate), "line_total": str(line_total)})
    return lines


def priced_total(project: Project, payload: OfferCreate) -> tuple[Decimal | None, list[dict] | None]:
    """(total, item_prices). One total: the amount as sent. Per item: a rate
    for every listed item, line total = rate x quantity (or the rate itself
    for an item with no quantity), total = the sum."""
    if project.pricing_basis != PricingBasis.per_item:
        return payload.amount, None
    items = {i.id for i in project.items}
    rates = {p.item_id: p.rate for p in payload.item_prices or []}
    if set(rates) != items or len(rates) != len(payload.item_prices or []):
        raise HTTPException(status_code=400, detail="Give a rate for every item listed in the requirement, once each.")
    lines = _lines(project, rates)
    return sum(Decimal(line["line_total"]) for line in lines), lines


def draft_pricing(project: Project, amount: Decimal | None, item_prices: list | None) -> tuple[Decimal | None, list[dict] | None]:
    """Stage 5.3: the commercial part of a draft, on the requirement's pricing
    basis (Stage 3.4) -- the same arithmetic as a submission, but it may be
    incomplete. One total: the amount entered, if any. Per item: rates for
    the items priced so far (only the requirement's own items, once each);
    the total is the server's sum, and only once every item has a rate --
    a partial sum is never presented as the offer's price. Raises 400 on a
    value that could never make a valid offer."""
    if project.pricing_basis != PricingBasis.per_item:
        if item_prices:
            raise HTTPException(status_code=400, detail="This requirement is priced as one total, not per item.")
        if amount is not None and not (Decimal(0) < amount < AMOUNT_LIMIT):
            raise HTTPException(status_code=400, detail="Enter a valid bid amount.")
        return amount, None
    items = {i.id for i in project.items}
    rates = {p.item_id: p.rate for p in item_prices or []}
    if len(rates) != len(item_prices or []):
        raise HTTPException(status_code=400, detail="Give a rate for every item listed in the requirement, once each.")
    if set(rates) - items:
        raise HTTPException(status_code=400, detail="That item isn't part of this requirement.")
    lines = _lines(project, rates)
    total = sum((Decimal(line["line_total"]) for line in lines), Decimal(0))
    if total >= AMOUNT_LIMIT:
        raise HTTPException(status_code=400, detail="Enter a valid bid amount.")
    return (total if set(rates) == items and total > 0 else None), lines


def check_commitment(project: Project, start: date | None, completion: date | None, duration: int | None) -> None:
    """Stage 5.5: the provider's execution commitment must make sense on its
    own, by the same rules as the owner's expected timing (Stage 3.7): a
    completion date or a duration, not both; a duration of 1 day to 10
    years; completion not before start; and no work before offers close
    (the response deadline, the server's own record). Raises 400."""
    from app.routers.projects import MAX_DURATION_DAYS

    if completion and duration:
        raise HTTPException(status_code=400, detail="Give either a completion date or a duration, not both.")
    if duration is not None and not 1 <= duration <= MAX_DURATION_DAYS:
        raise HTTPException(status_code=400, detail=f"Duration must be between 1 and {MAX_DURATION_DAYS} days.")
    if start and completion and completion < start:
        raise HTTPException(status_code=400, detail="The completion date can't be before the start date.")
    response_closes = project.bid_deadline.date()
    if start and start < response_closes:
        raise HTTPException(status_code=400, detail="Work can't start before the response deadline.")
    if completion and completion < response_closes:
        raise HTTPException(status_code=400, detail="Work can't finish before the response deadline.")


def timing_conflicts(project: Project, offer) -> list[str]:
    """Stage 5.5: where the provider's commitment differs from what the owner
    expects (Stage 3.7), against the requirement as it now is -- flagged for
    the provider to see, never changed:
      starts_later    proposed start after the expected start
      finishes_later  finishing after the expected completion (a completion
                      date, or start + duration on either side)
      takes_longer    more days than the expected duration"""
    def finish(start, completion, duration):
        return completion or (start + timedelta(days=duration) if start and duration else None)

    def span(start, completion, duration):
        return duration or ((completion - start).days if start and completion else None)

    mine = (offer.proposed_start_date, offer.proposed_completion_date, offer.proposed_duration_days)
    theirs = (project.expected_start_date, project.expected_completion_date, project.expected_duration_days)
    conflicts = []
    if mine[0] and theirs[0] and mine[0] > theirs[0]:
        conflicts.append("starts_later")
    if (f := finish(*mine)) and (g := finish(*theirs)) and f > g:
        conflicts.append("finishes_later")
    if theirs[2] and (s := span(*mine)) is not None and s > theirs[2]:
        conflicts.append("takes_longer")
    return conflicts


def _side_documents(db: Session, project_id: str, organization_id: str | None, provider_id: str):
    """The attachments of one side's response: its organization's (whichever
    member uploaded them), or an individual's own."""
    query = db.query(OfferDocument).filter(OfferDocument.project_id == project_id)
    if organization_id:
        return query.filter(OfferDocument.organization_id == organization_id)
    return query.filter(OfferDocument.organization_id.is_(None), OfferDocument.service_provider_id == provider_id)


def _committed(db: Session, project_id: str, organization_id: str | None, provider_id: str) -> bool:
    """Stage 5.5: the side's offer states when it will finish -- a completion
    date or a duration (saved on the draft) -- which answers a required
    completion period as well as the free text does."""
    from app.models.offer import Offer

    query = db.query(Offer).filter(Offer.project_id == project_id)
    query = query.filter(Offer.organization_id == organization_id) if organization_id else query.filter(Offer.organization_id.is_(None), Offer.service_provider_id == provider_id)
    offer = query.first()
    return bool(offer and (offer.proposed_completion_date or offer.proposed_duration_days))


def check_complete(
    db: Session, project: Project, organization_id: str | None, provider_id: str, payload: OfferCreate
) -> list[str]:
    """Raises 400 naming what's missing; returns the declarations accepted."""
    reqs = requirements_for(project)
    missing = []
    if reqs.completion_period == "required" and not (payload.timeline_estimate or "").strip() and not _committed(db, project.id, organization_id, provider_id):
        missing.append("a completion period")
    if reqs.approach == "required" and not (payload.message or "").strip():
        missing.append("your technical approach")
    required_docs = {d.name for d in reqs.documents if d.required}
    if required_docs:
        attached = {d.label for d in _side_documents(db, project.id, organization_id, provider_id)}
        missing += [f'the "{name}" document' for name in sorted(required_docs - attached)]
    if reqs.declarations and set(payload.accepted_declarations) != set(reqs.declarations):
        missing.append("acceptance of every declaration")
    if missing:
        raise HTTPException(status_code=400, detail="Your offer is missing " + ", ".join(missing) + ".")
    return list(reqs.declarations)


def documents_out(db: Session, project_id: str, organization_id: str | None, provider_id: str) -> list[OfferDocumentOut]:
    storage = get_storage()
    rows = _side_documents(db, project_id, organization_id, provider_id).order_by(OfferDocument.label.asc()).all()
    return [
        OfferDocumentOut(
            id=d.id,
            label=d.label,
            file_name=d.file_name,
            uploaded_at=d.uploaded_at,
            url=storage.signed_url(OFFER_DOCUMENTS_BUCKET, d.file_path, _LINK_SECONDS),
        )
        for d in rows
    ]
