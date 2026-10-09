"""Stage 7.8: variations -- agreed changes to the work after the agreement is
in force.

Either party proposes a change: what changes in the scope, quantities or
specification (always described), and optionally a change to the agreed
value, a revised completion date, a revised due date for one deliverable, or
an added deliverable. Nothing takes effect until the OTHER party agrees; the
proposer may withdraw it while open, the other party may reject it. One
proposal is open at a time. When agreed, the current agreed state moves on --
the value and completion are derived from the original award plus the agreed
variations, and a deliverable's revised date or an added deliverable is
applied -- while each variation keeps what it changed from. The award, the
requirement, the winning offer and the original agreement are never
rewritten. Every action is under the requirement's lock with the variation's
version; audit-logged; the other party is told."""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models.agreement import Agreement, Milestone, Variation
from app.models.enums import NotificationType
from app.models.user import User
from app.routers.agreements import _best_effort, _check_version, _load, _out, _record, _touch, current_terms, planned_completion
from app.schemas.agreement import AgreementOut, MilestoneNote, VariationIn
from app.services import audit
from app.services import notify as notify_service

router = APIRouter(prefix="/projects/{project_id}/agreement/variations", tags=["agreements"])

LATEST = "This page now shows the latest."


def _variation(db: Session, agreement: Agreement, variation_id: str) -> Variation:
    v = db.get(Variation, variation_id)
    if not v or v.agreement_id != agreement.id:
        raise HTTPException(status_code=404, detail="Change not found.")
    db.refresh(v)  # judged under the requirement's lock
    return v


def _in_force(agreement: Agreement) -> None:
    if agreement.status == "terminated":
        raise HTTPException(status_code=400, detail=f"This agreement has been terminated. {LATEST}")
    if agreement.completion_status in ("submitted", "accepted"):  # Stage 7.10: the work as submitted is what is reviewed
        raise HTTPException(status_code=409, detail=f"The work was submitted as complete, so the agreed work can't change now. {LATEST}")
    if agreement.status != "active":
        raise HTTPException(status_code=400, detail="Changes are recorded once the agreement is in force. Until then, edit the agreement and its deliverables directly.")


def _check(v: Variation, if_match: str | None) -> None:
    if if_match and if_match.strip('"') != str(v.version):
        raise HTTPException(
            status_code=409,
            detail=f"This change was updated by someone else (the other party, a colleague or another tab) while you had it open. {LATEST} Check it, then try again if still needed.",
        )


def _still_open(v: Variation) -> None:
    if v.status != "proposed":
        said = {"agreed": "agreed", "rejected": "rejected", "withdrawn": "withdrawn", "lapsed": "closed when the agreement ended"}[v.status]
        raise HTTPException(status_code=409, detail=f"This change was already {said}. {LATEST}")


def _tell(db: Session, project, winner, to: str, state: str, state_ar: str) -> None:
    def send():
        if to == "provider":
            notify_service.notify_team(
                db, db.get(User, winner.service_provider_id), NotificationType.variation_updated,
                link=f"/service-provider/projects/{project.id}/offer", organization_id=winner.organization_id,
                project_title=project.title, state=state, state_ar=state_ar,
            )
        else:
            notify_service.notify_team(
                db, db.get(User, project.owner_id), NotificationType.variation_updated,
                link=f"/owner/projects/{project.id}", organization_id=project.organization_id,
                project_title=project.title, state=state, state_ar=state_ar,
            )

    _best_effort(db, send, f"variation notifications for {project.id}")


def _other(side: str) -> str:
    return "provider" if side == "owner" else "owner"


@router.post("", response_model=AgreementOut)
def propose_variation(
    project_id: str, payload: VariationIn, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    if side == "admin":
        raise HTTPException(status_code=403, detail="Only the parties to the agreement can change it.")
    _in_force(agreement)
    if db.query(Variation.id).filter(Variation.agreement_id == agreement.id, Variation.status == "proposed").first():
        raise HTTPException(status_code=409, detail=f"A proposed change is already awaiting an answer. Agree, reject or withdraw it first. {LATEST}")
    _check_version(agreement, if_match)
    description = payload.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="Describe the change.")
    if payload.value_change is not None and payload.value_change == 0:
        raise HTTPException(status_code=400, detail="A change to the value can't be zero. Leave it empty if the value stays the same.")
    variations = db.query(Variation).filter(Variation.agreement_id == agreement.id).all()
    if payload.value_change is not None:
        amount, _ = current_terms(award, None, variations)
        if amount + payload.value_change <= 0:
            raise HTTPException(status_code=400, detail="The agreed value can't fall to zero or below.")
    awarded_on = award.created_at.date()
    if payload.completion_date and payload.completion_date < awarded_on:
        raise HTTPException(status_code=400, detail="A revised date can't be before the award.")
    milestone = None
    if payload.milestone_id or payload.milestone_due_date:
        milestone = db.get(Milestone, payload.milestone_id) if payload.milestone_id else None
        if not milestone or milestone.agreement_id != agreement.id:
            raise HTTPException(status_code=404, detail="Deliverable not found.")
        if milestone.status == "accepted":
            raise HTTPException(status_code=400, detail="An accepted deliverable can't be rescheduled.")
        if not payload.milestone_due_date or payload.milestone_due_date < awarded_on:
            raise HTTPException(status_code=400, detail="A revised date can't be before the award.")
    added = (payload.add_deliverable or "").strip() or None
    last = db.query(Variation.number).filter(Variation.agreement_id == agreement.id).order_by(Variation.number.desc()).first()
    v = Variation(
        agreement_id=agreement.id, number=(last[0] if last else 0) + 1, description=description,
        value_change=payload.value_change, completion_date=payload.completion_date,
        milestone_id=milestone.id if milestone else None, milestone_due_date=payload.milestone_due_date if milestone else None,
        add_deliverable=added, proposed_party=side, proposed_by=user.id, proposed_at=datetime.utcnow().replace(microsecond=0),
    )
    db.add(v)
    db.flush()
    _record(db, agreement, "change_proposed", side, user, description, v.proposed_at, variation_id=v.id)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="variation.propose", target_type="agreement", target_id=agreement.id,
                     new_value=f"V{v.number}:{v.id} value:{v.value_change} completion:{v.completion_date} milestone:{v.milestone_id}->{v.milestone_due_date} add:{added}",
                     reason=description)
    _tell(db, project, winner, _other(side), "proposed", "اقتُرح")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/{variation_id}/agree", response_model=AgreementOut)
def agree_variation(
    project_id: str, variation_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The other party agrees: the change takes effect now, on top of the
    current agreed state, keeping what it changed from."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    v = _variation(db, agreement, variation_id)
    _still_open(v)
    if side == "admin" or side == v.proposed_party:
        raise HTTPException(status_code=403, detail="A change takes effect only when the other party agrees to it.")
    _in_force(agreement)
    _check(v, if_match)
    variations = db.query(Variation).filter(Variation.agreement_id == agreement.id).all()
    original_completion, _ = planned_completion(project, winner)
    amount, completion = current_terms(award, original_completion, variations)
    if v.value_change is not None and amount + v.value_change <= 0:
        raise HTTPException(status_code=400, detail="The agreed value can't fall to zero or below.")
    milestone = db.get(Milestone, v.milestone_id) if v.milestone_id else None
    if v.milestone_id and (not milestone or milestone.status == "accepted"):
        raise HTTPException(status_code=409, detail=f"The deliverable this change reschedules was accepted meanwhile. Reject this change and propose a new one if needed. {LATEST}")
    now = datetime.utcnow().replace(microsecond=0)
    v.status, v.decided_party, v.decided_by, v.decided_at = "agreed", side, user.id, now
    v.decision_note = (payload.note or "").strip() or None
    v.previous_amount, v.resulting_amount = amount, amount + (v.value_change or Decimal(0))
    v.previous_completion_date = completion if v.completion_date else None
    if milestone:
        v.previous_milestone_due_date = milestone.due_date
        milestone.due_date, milestone.version = v.milestone_due_date, milestone.version + 1
        milestone.updated_at = now
    if v.add_deliverable:
        last = db.query(Milestone.position).filter(Milestone.agreement_id == agreement.id).order_by(Milestone.position.desc()).first()
        db.add(Milestone(agreement_id=agreement.id, position=(last[0] if last else 0) + 1, title=v.add_deliverable,
                         description=v.description, created_by=user.id, variation_id=v.id))
    v.version += 1
    _record(db, agreement, "change_agreed", side, user, v.decision_note, now, variation_id=v.id)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="variation.agree", target_type="agreement", target_id=agreement.id,
                     previous_value=f"V{v.number} amount:{v.previous_amount} completion:{v.previous_completion_date} milestone_due:{v.previous_milestone_due_date}",
                     new_value=f"V{v.number} amount:{v.resulting_amount} completion:{v.completion_date} milestone_due:{v.milestone_due_date}",
                     reason=v.decision_note)
    _tell(db, project, winner, v.proposed_party, "agreed", "تمت الموافقة على")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/{variation_id}/reject", response_model=AgreementOut)
def reject_variation(
    project_id: str, variation_id: str, payload: MilestoneNote, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    v = _variation(db, agreement, variation_id)
    _still_open(v)
    if side == "admin" or side == v.proposed_party:
        raise HTTPException(status_code=403, detail="Only the other party can reject a proposed change. Withdraw your own instead.")
    _check(v, if_match)
    v.status, v.decided_party, v.decided_by, v.decided_at = "rejected", side, user.id, datetime.utcnow().replace(microsecond=0)
    v.decision_note = (payload.note or "").strip() or None
    v.version += 1
    _record(db, agreement, "change_rejected", side, user, v.decision_note, v.decided_at, variation_id=v.id)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="variation.reject", target_type="agreement", target_id=agreement.id,
                     new_value=f"V{v.number}:rejected", reason=v.decision_note)
    _tell(db, project, winner, v.proposed_party, "rejected", "رُفض")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/{variation_id}/withdraw", response_model=AgreementOut)
def withdraw_variation(
    project_id: str, variation_id: str, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    v = _variation(db, agreement, variation_id)
    _still_open(v)
    if side != v.proposed_party:
        raise HTTPException(status_code=403, detail="Only the side that proposed a change can withdraw it.")
    _check(v, if_match)
    v.status, v.decided_party, v.decided_by, v.decided_at = "withdrawn", side, user.id, datetime.utcnow().replace(microsecond=0)
    v.version += 1
    _record(db, agreement, "change_withdrawn", side, user, None, v.decided_at, variation_id=v.id)
    _touch(agreement, user)
    audit.log_action(db, actor_id=user.id, action="variation.withdraw", target_type="agreement", target_id=agreement.id, new_value=f"V{v.number}:withdrawn")
    _tell(db, project, winner, _other(side), "withdrawn", "سُحب")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)
