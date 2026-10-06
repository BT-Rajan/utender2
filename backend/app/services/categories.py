"""The platform's service categories (admin-managed) and how requirements and
providers refer to them."""
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.category import ServiceCategory
from app.models.project import Project
from app.services.locations import KUWAIT_GOVERNORATES


def active_categories(db: Session) -> list[ServiceCategory]:
    return db.query(ServiceCategory).filter(ServiceCategory.is_active.is_(True)).order_by(ServiceCategory.name.asc()).all()


def resolve_trade(db: Session, category_id: str | None, trade: str | None) -> tuple[str | None, str | None]:
    """(category_id, trade) for a requirement. A chosen category sets the
    shown name; free text that matches a category's name links it; any other
    text stays free text (no category, so category matching can't apply)."""
    if category_id:
        category = db.get(ServiceCategory, category_id)
        if not category or not category.is_active:
            raise HTTPException(status_code=400, detail="Choose a type of work from the platform's list.")
        return category.id, category.name
    text = (trade or "").strip() or None
    if text:
        match = (
            db.query(ServiceCategory)
            .filter(ServiceCategory.is_active.is_(True), func.lower(ServiceCategory.name) == text.lower())
            .first()
        )
        if match:
            return match.id, match.name
    return None, text


def rename_category(db: Session, category: ServiceCategory, name: str) -> None:
    category.name = name
    # Keep the shown name of every requirement filed under it in step.
    db.query(Project).filter(Project.category_id == category.id).update({Project.trade: name}, synchronize_session=False)


def clean_services(db: Session, categories: list[str], governorates: list[str]) -> tuple[list[str], list[str]]:
    allowed = {c.id for c in active_categories(db)}
    if any(c not in allowed for c in categories):
        raise HTTPException(status_code=400, detail="Choose services from the platform's list.")
    if any(g not in KUWAIT_GOVERNORATES for g in governorates):
        raise HTTPException(status_code=400, detail="Choose governorates from the list.")
    return list(dict.fromkeys(categories)), list(dict.fromkeys(governorates))
