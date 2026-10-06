from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.enums import StakeholderType
from app.models.user import User
from app.schemas.stakeholder import IdentityOut, StakeholderEstablish
from app.services import stakeholder as stakeholder_service

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/identity", response_model=IdentityOut)
def get_identity(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Who is logged in, who they act as, and how far that stakeholder is
    from being able to participate."""
    return stakeholder_service.identity(user, db)


@router.put("/stakeholder", response_model=IdentityOut)
def set_stakeholder(payload: StakeholderEstablish, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Establish (or, before review, correct) whether this account represents
    the person themselves or an organization they are authorized to act for."""
    if payload.type == StakeholderType.organization and not payload.authorized:
        raise HTTPException(status_code=400, detail="Confirm that you are authorized to act for this organization.")
    stakeholder_service.establish(user, db, payload.type, payload.legal_name, payload.position)
    return stakeholder_service.identity(user, db)
