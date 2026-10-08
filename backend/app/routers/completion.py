"""Stage 7.10: the whole work's completion and the owner's acceptance.

The winning provider's side submits the work as complete -- once the work
has started, is not on hold, every deliverable of the agreement (if it has
any) is accepted and no proposed change is awaiting an answer. The owner
side accepts it, or returns it for correction with a note; returned work can
be submitted again. Submitted is not accepted, and accepted is not yet the
transaction's closure (Stage 7.11 builds on accepted work). Each step is
recorded on the agreement and as an execution-history entry (delivered /
accepted / returned, with no deliverable), audit-logged, and the other party
is told. Under the requirement's lock with the agreement's version; a
repeated or late action is explained, never applied twice."""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.agreement import Milestone, Variation
from app.models.enums import NotificationType
from app.models.user import User
from app.routers.agreements import _best_effort, _check_version, _load, _out, _record, _require_owner, _touch
from app.schemas.agreement import AgreementOut, MilestoneNote
from app.services import audit
from app.services import notify as notify_service

router = APIRouter(prefix="/projects/{project_id}/agreement/completion", tags=["agreements"])

LATEST = "This page now shows the latest."


def _tell(db: Session, project, winner, to: str, state: str, state_ar: str) -> None:
    def send():
        if to == "provider":
            notify_service.notify_team(
                db, db.get(User, winner.service_provider_id), NotificationType.execution_updated,
                link=f"/service-provider/projects/{project.id}/offer", organization_id=winner.organization_id,
                project_title=project.title, state=state, state_ar=state_ar,
            )
        else:
            notify_service.notify_team(
                db, db.get(User, project.owner_id), NotificationType.execution_updated,
                link=f"/owner/projects/{project.id}", organization_id=project.organization_id,
                project_title=project.title, state=state, state_ar=state_ar,
            )

    _best_effort(db, send, f"completion notifications for {project.id}")


def _not_terminated(agreement) -> None:
    if agreement.status == "terminated":
        raise HTTPException(status_code=400, detail=f"This agreement has been terminated. {LATEST}")


@router.post("/submit", response_model=AgreementOut)
def submit_completion(
    project_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    if side != "provider":
        raise HTTPException(status_code=403, detail="Only the service provider submits the work as complete.")
    _not_terminated(agreement)
    if agreement.completion_status == "submitted":
        raise HTTPException(status_code=409, detail=f"The work was already submitted as complete (by a colleague or from another tab) and is awaiting review. {LATEST}")
    if agreement.completion_status == "accepted":
        raise HTTPException(status_code=409, detail=f"The work was already accepted as complete. {LATEST}")
    if agreement.work_started_at is None:
        raise HTTPException(status_code=400, detail="The work hasn't started yet. Record its start first.")
    if agreement.on_hold_at is not None:
        raise HTTPException(status_code=400, detail=f"The work is on hold. Resume it first. {LATEST}")
    outstanding = db.query(Milestone).filter(Milestone.agreement_id == agreement.id, Milestone.status != "accepted").count()
    if outstanding:
        raise HTTPException(status_code=400, detail="Every deliverable must be accepted before the work is submitted as complete.")
    if db.query(Variation.id).filter(Variation.agreement_id == agreement.id, Variation.status == "proposed").first():
        raise HTTPException(status_code=400, detail="A proposed change is still awaiting an answer. Settle it first.")
    _check_version(agreement, if_match)
    now = datetime.utcnow().replace(microsecond=0)
    agreement.completion_status, agreement.completion_submitted_at, agreement.completion_submitted_by = "submitted", now, user.id
    agreement.completion_note = (payload.note or "").strip() or None
    agreement.completion_decided_at = agreement.completion_decided_by = agreement.completion_decision_note = None
    _record(db, agreement, "delivered", side, user, agreement.completion_note, now)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="completion.submit", target_type="agreement", target_id=agreement.id,
                     new_value="submitted", reason=agreement.completion_note)
    _tell(db, project, winner, "owner", "submitted as complete", "تم تقديم")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


def _decide(db: Session, project_id: str, user: User, note: str | None, if_match: str | None, accept: bool):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    _not_terminated(agreement)
    if agreement.completion_status == "accepted":
        raise HTTPException(status_code=409, detail=f"The work was already accepted as complete (by a colleague or from another tab). {LATEST}")
    if agreement.completion_status == "returned":
        raise HTTPException(status_code=409, detail=f"The work was already returned for correction (by a colleague or from another tab). {LATEST}")
    if agreement.completion_status != "submitted":
        raise HTTPException(status_code=400, detail="The work hasn't been submitted as complete yet.")
    _check_version(agreement, if_match)
    note = (note or "").strip() or None
    if not accept and not note:
        raise HTTPException(status_code=400, detail="Say what needs correcting.")
    now = datetime.utcnow().replace(microsecond=0)
    kind = "accepted" if accept else "returned"
    agreement.completion_status, agreement.completion_decided_at, agreement.completion_decided_by = kind, now, user.id
    agreement.completion_decision_note = note
    _record(db, agreement, kind, side, user, note, now)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action=f"completion.{'accept' if accept else 'return'}", target_type="agreement",
                     target_id=agreement.id, previous_value="submitted", new_value=kind, reason=note)
    _tell(db, project, winner, "provider", "accepted as complete" if accept else "returned for correction",
          "تم قبول" if accept else "تمت إعادة")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/accept", response_model=AgreementOut)
def accept_completion(
    project_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _decide(db, project_id, user, payload.note, if_match, accept=True)


@router.post("/return", response_model=AgreementOut)
def return_completion(
    project_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return _decide(db, project_id, user, payload.note, if_match, accept=False)
