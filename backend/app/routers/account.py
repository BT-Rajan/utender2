from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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


# ---------- organization members (everything is shared among them: services.team) ----------


class MemberOut(BaseModel):
    user_id: str
    full_name: str | None
    email: str
    role: str
    position: str | None


class MemberAdd(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    position: str | None = Field(default=None, max_length=150)


@router.get("/organization/members", response_model=list[MemberOut])
def list_members(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return stakeholder_service.list_members(user, db)


@router.post("/organization/members", response_model=list[MemberOut], status_code=201)
def add_member(payload: MemberAdd, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stakeholder_service.add_member(user, db, payload.email, payload.position)
    db.commit()
    return stakeholder_service.list_members(user, db)


@router.delete("/organization/members/{member_id}", response_model=list[MemberOut])
def remove_member(member_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stakeholder_service.remove_member(user, db, member_id)
    db.commit()
    return stakeholder_service.list_members(user, db)
