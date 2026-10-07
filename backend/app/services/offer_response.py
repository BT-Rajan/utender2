"""Stage 3.8: what a provider's response must contain, checked against the
requirement's response rules (Project.response_requirements) and its pricing
basis (Stage 3.4). Used by the existing offer submission -- there is one offer
system; this only decides whether a submission is complete."""
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


def _side_documents(db: Session, project_id: str, organization_id: str | None, provider_id: str):
    """The attachments of one side's response: its organization's (whichever
    member uploaded them), or an individual's own."""
    query = db.query(OfferDocument).filter(OfferDocument.project_id == project_id)
    if organization_id:
        return query.filter(OfferDocument.organization_id == organization_id)
    return query.filter(OfferDocument.organization_id.is_(None), OfferDocument.service_provider_id == provider_id)


def check_complete(
    db: Session, project: Project, organization_id: str | None, provider_id: str, payload: OfferCreate
) -> list[str]:
    """Raises 400 naming what's missing; returns the declarations accepted."""
    reqs = requirements_for(project)
    missing = []
    if reqs.completion_period == "required" and not (payload.timeline_estimate or "").strip():
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
