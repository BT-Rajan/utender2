"""Stage 7.7: an agreement's deliverables (milestones).

Where the awarded work naturally has deliverables, the owner side sets them
out while the agreement is being prepared -- optionally from the
requirement's own items -- and the winning provider sees them before agreeing.
Once the agreement is in force they are what was agreed: nobody rewrites them
(changes are a later stage's variations). After the work has started, the
winning provider delivers each; the owner side accepts it or returns it for
correction, and a returned one can be delivered again. Delivered is not
accepted. Evidence is an agreement document linked to the deliverable (7.4);
each event goes into the parties' execution history (7.6) and the audit log,
and the other party is told. Every action is under the requirement's lock,
with the deliverable's version against stale pages."""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.agreement import Agreement, AgreementDocument, Milestone
from app.models.enums import NotificationType
from app.models.project import ProjectItem
from app.models.user import User
from app.routers.agreements import _best_effort, _check_version, _clear_confirmation, _load, _out, _record, _require_owner, _touch, require_in_force
from app.schemas.agreement import AgreementOut, MilestoneIn, MilestoneNote
from app.services import audit
from app.services import notify as notify_service

router = APIRouter(prefix="/projects/{project_id}/agreement/milestones", tags=["agreements"])

MAX_MILESTONES = 50
LATEST = "This page now shows the latest."


def _milestone(db: Session, agreement: Agreement, milestone_id: str) -> Milestone:
    """One of THIS agreement's deliverables -- any other id is not found."""
    m = db.get(Milestone, milestone_id)
    if not m or m.agreement_id != agreement.id:
        raise HTTPException(status_code=404, detail="Deliverable not found.")
    db.refresh(m)  # judged under the requirement's lock, never on a stale read
    return m


def _check(m: Milestone, if_match: str | None) -> None:
    if if_match and if_match.strip('"') != str(m.version):
        raise HTTPException(
            status_code=409,
            detail=f"This deliverable was changed by someone else (the other party, a colleague or another tab) while you had it open. {LATEST} Check it, then try again if still needed.",
        )


def _editable(agreement: Agreement) -> None:
    if agreement.status != "preparing":
        raise HTTPException(status_code=400, detail=f"Deliverables are fixed once the agreement is in force or terminated. {LATEST}")


def _fields(db: Session, project, award, payload: MilestoneIn) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Give the deliverable a name.")
    if payload.due_date and payload.due_date < award.created_at.date():
        raise HTTPException(status_code=400, detail="A due date can't be before the award.")
    if payload.project_item_id:
        item = db.get(ProjectItem, payload.project_item_id)
        if not item or item.project_id != project.id:
            raise HTTPException(status_code=400, detail="That item isn't part of this requirement.")
    return {
        "title": title,
        "description": (payload.description or "").strip() or None,
        "due_date": payload.due_date,
        "project_item_id": payload.project_item_id or None,
    }


def _bump(m: Milestone) -> None:
    m.version += 1
    m.updated_at = datetime.utcnow().replace(microsecond=0)


def _tell(db: Session, project, winner, to: str, state: str, state_ar: str) -> None:
    def send():
        if to == "provider":
            notify_service.notify_team(
                db, db.get(User, winner.service_provider_id), NotificationType.milestone_updated,
                link=f"/service-provider/projects/{project.id}/offer", organization_id=winner.organization_id,
                project_title=project.title, state=state, state_ar=state_ar,
            )
        else:
            notify_service.notify_team(
                db, db.get(User, project.owner_id), NotificationType.milestone_updated,
                link=f"/owner/projects/{project.id}", organization_id=project.organization_id,
                project_title=project.title, state=state, state_ar=state_ar,
            )

    _best_effort(db, send, f"deliverable notifications for {project.id}")


@router.post("", response_model=AgreementOut)
def add_milestone(
    project_id: str, payload: MilestoneIn, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The owner side adds a deliverable while the agreement is being prepared."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    _editable(agreement)
    _check_version(agreement, if_match)
    fields = _fields(db, project, award, payload)
    count = db.query(Milestone).filter(Milestone.agreement_id == agreement.id).count()
    if count >= MAX_MILESTONES:
        raise HTTPException(status_code=400, detail="An agreement can have at most 50 deliverables.")
    last = db.query(Milestone.position).filter(Milestone.agreement_id == agreement.id).order_by(Milestone.position.desc()).first()
    m = Milestone(agreement_id=agreement.id, position=(last[0] if last else 0) + 1, created_by=user.id, **fields)
    db.add(m)
    _clear_confirmation(agreement)
    _touch(agreement, user)
    db.flush()
    audit.log_action(db, actor_id=user.id, action="milestone.create", target_type="agreement", target_id=agreement.id, new_value=f"{m.id}:{m.title}")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.patch("/{milestone_id}", response_model=AgreementOut)
def edit_milestone(
    project_id: str, milestone_id: str, payload: MilestoneIn, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    m = _milestone(db, agreement, milestone_id)
    _editable(agreement)
    _check(m, if_match)
    if m.status != "pending":  # Batch A: what was delivered or decided stays as it was
        raise HTTPException(status_code=400, detail="A deliverable that was delivered or decided can't be rewritten.")
    fields = _fields(db, project, award, payload)
    before = f"{m.title} due:{m.due_date}"
    for k, v in fields.items():
        setattr(m, k, v)
    _bump(m)
    _clear_confirmation(agreement)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="milestone.update", target_type="agreement", target_id=agreement.id,
                     previous_value=f"{m.id}:{before}", new_value=f"{m.id}:{m.title} due:{m.due_date}")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.delete("/{milestone_id}", response_model=AgreementOut)
def remove_milestone(
    project_id: str, milestone_id: str, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    m = _milestone(db, agreement, milestone_id)
    _editable(agreement)
    _check(m, if_match)
    if m.status != "pending" or db.query(AgreementDocument.id).filter(AgreementDocument.milestone_id == m.id).first():
        raise HTTPException(status_code=400, detail="A deliverable that was delivered or has evidence stays on record.")
    title = m.title
    db.delete(m)
    _clear_confirmation(agreement)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="milestone.remove", target_type="agreement", target_id=agreement.id, previous_value=f"{milestone_id}:{title}")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/{milestone_id}/deliver", response_model=AgreementOut)
def deliver_milestone(
    project_id: str, milestone_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The winning provider's side delivers it -- once the work has started,
    not while it is on hold, not once the agreement is terminated."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    if side != "provider":
        raise HTTPException(status_code=403, detail="Only the service provider delivers a deliverable.")
    m = _milestone(db, agreement, milestone_id)
    require_in_force(agreement)
    if agreement.work_started_at is None:
        raise HTTPException(status_code=400, detail="The work hasn't started yet. Record its start first.")
    if agreement.on_hold_at is not None:
        raise HTTPException(status_code=400, detail=f"The work is on hold. Resume it before delivering. {LATEST}")
    if m.status == "delivered":
        raise HTTPException(status_code=409, detail=f"This deliverable was already delivered (by a colleague or from another tab) and is awaiting review. {LATEST}")
    if m.status == "accepted":
        raise HTTPException(status_code=409, detail=f"This deliverable was already accepted. {LATEST}")
    _check(m, if_match)
    now = datetime.utcnow().replace(microsecond=0)
    m.status, m.delivered_at, m.delivered_by = "delivered", now, user.id
    m.delivery_note = (payload.note or "").strip() or None
    m.decided_at = m.decided_by = m.decision_note = None  # a fresh delivery awaits a fresh review
    _bump(m)
    _record(db, agreement, "delivered", side, user, m.delivery_note, now, m.id)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="milestone.deliver", target_type="agreement", target_id=agreement.id,
                     new_value=f"{m.id}:delivered", reason=m.delivery_note)
    _tell(db, project, winner, "owner", "delivered", "تم تسليم")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


def _decide(db: Session, project_id: str, milestone_id: str, user: User, note: str | None, if_match: str | None, accept: bool):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    m = _milestone(db, agreement, milestone_id)
    require_in_force(agreement)
    if m.status == "accepted":
        raise HTTPException(status_code=409, detail=f"This deliverable was already accepted (by a colleague or from another tab). {LATEST}")
    if m.status == "returned":
        raise HTTPException(status_code=409, detail=f"This deliverable was already returned for correction (by a colleague or from another tab). {LATEST}")
    if m.status != "delivered":
        raise HTTPException(status_code=400, detail="This deliverable hasn't been delivered yet.")
    _check(m, if_match)
    note = (note or "").strip() or None
    if not accept and not note:
        raise HTTPException(status_code=400, detail="Say what needs correcting.")
    now = datetime.utcnow().replace(microsecond=0)
    kind = "accepted" if accept else "returned"
    m.status, m.decided_at, m.decided_by, m.decision_note = kind, now, user.id, note
    _bump(m)
    _record(db, agreement, kind, side, user, note, now, m.id)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action=f"milestone.{'accept' if accept else 'return'}", target_type="agreement",
                     target_id=agreement.id, previous_value=f"{m.id}:delivered", new_value=f"{m.id}:{kind}", reason=note)
    _tell(db, project, winner, "provider", "accepted" if accept else "returned for correction", "تم قبول" if accept else "تمت إعادة")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/{milestone_id}/accept", response_model=AgreementOut)
def accept_milestone(
    project_id: str, milestone_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _decide(db, project_id, milestone_id, user, payload.note, if_match, accept=True)


@router.post("/{milestone_id}/return", response_model=AgreementOut)
def return_milestone(
    project_id: str, milestone_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _decide(db, project_id, milestone_id, user, payload.note, if_match, accept=False)
