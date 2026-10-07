from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.enums import StakeholderType
from app.models.user import User
from app.config import get_settings
from app.schemas.common import UTCDateTime
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


class InvitationCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    position: str | None = Field(default=None, max_length=150)


class InvitationOut(BaseModel):
    id: str
    email: str
    position: str | None
    expires_at: UTCDateTime
    link: str | None = None  # only when just created: the representative may also share it directly


class InvitationView(BaseModel):
    organization_name: str
    email: str
    role: str
    invited_by: str | None
    expires_at: UTCDateTime
    account_exists: bool


@router.get("/organization/members", response_model=list[MemberOut])
def list_members(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return stakeholder_service.list_members(user, db)


@router.get("/organization/invitations", response_model=list[InvitationOut])
def list_invitations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [
        InvitationOut(id=i.id, email=i.email, position=i.position, expires_at=i.expires_at)
        for i in stakeholder_service.pending_invitations(user, db)
    ]


@router.post("/organization/invitations", response_model=InvitationOut, status_code=201)
def invite(payload: InvitationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Invite a colleague by email, whether or not they have an account yet.
    They join only by accepting, signed in with that email."""
    invitation, token = stakeholder_service.invite_member(user, db, payload.email, payload.position)
    db.commit()
    return InvitationOut(
        id=invitation.id,
        email=invitation.email,
        position=invitation.position,
        expires_at=invitation.expires_at,
        link=f"{get_settings().app_url}/invite/{token}",
    )


@router.delete("/organization/invitations/{invitation_id}", status_code=204)
def withdraw_invitation(invitation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stakeholder_service.revoke_invitation(user, db, invitation_id)
    db.commit()


@router.get("/invitations/{token}", response_model=InvitationView)
def view_invitation(token: str, db: Session = Depends(get_db)):
    """What an invitation link shows before signing in (no account needed)."""
    return stakeholder_service.describe_invitation(db, token)


@router.post("/invitations/{token}/accept", response_model=IdentityOut)
def accept_invitation(token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stakeholder_service.accept_invitation(user, db, token)
    db.commit()
    return stakeholder_service.identity(user, db)


@router.delete("/organization/members/{member_id}", response_model=list[MemberOut])
def remove_member(member_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stakeholder_service.remove_member(user, db, member_id)
    db.commit()
    return stakeholder_service.list_members(user, db)
