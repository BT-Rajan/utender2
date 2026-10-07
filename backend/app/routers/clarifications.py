from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_owner
from app.models.clarification import Clarification
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import NotificationType, UserRole
from app.models.project import Project
from app.models.user import User
from app.routers.projects import _can_view_project
from app.services.tender_rules import questions_closed_reason, questions_open
from app.schemas.clarification import ClarificationAnswer, ClarificationCreate, ClarificationOut
from app.services.email import notify_clarification_answered, notify_owner_new_clarification
from app.services.notify import notify
from app.services.tender_lifecycle import is_sealed_and_open

router = APIRouter(prefix="/projects/{project_id}/clarifications", tags=["clarifications"])


def _serialize(c: Clarification, company_name: str | None, redact: bool = False) -> ClarificationOut:
    return ClarificationOut(
        id=c.id,
        project_id=c.project_id,
        service_provider_id=None if redact else c.service_provider_id,
        question=c.question,
        answer=c.answer,
        shared_with_all=c.shared_with_all,
        created_at=c.created_at,
        answered_at=c.answered_at,
        service_provider_company_name=None if redact else company_name,
    )


# Visibility (spec §2.7, D-008): admin sees everything. A service provider always
# sees their own questions (answer pending or not, shared or private) —
# but another service provider's question is visible only once it's both
# answered AND marked shared_with_all, so an unanswered or deliberately
# private Q&A never leaks to the rest of the field. The owner sees every
# question too, EXCEPT that while the tender is sealed and still open
# (spec §19-21, D-001: bidder identity hidden from the owner until close),
# a question from anyone other than the owner's own reading of it has its
# service_provider_id/company_name redacted the same way owner.py's offers list
# already does — otherwise the sealed-bid rule would be enforced on bids
# but bypassable by simply asking a question instead (found in PASS 17's
# security audit).
@router.get("", response_model=list[ClarificationOut])
def list_clarifications(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")

    rows = (
        db.query(Clarification, ServiceProviderProfile)
        .join(ServiceProviderProfile, Clarification.service_provider_id == ServiceProviderProfile.user_id)
        .filter(Clarification.project_id == project_id)
        .order_by(Clarification.created_at.asc())
        .all()
    )

    is_admin = user.role == UserRole.admin
    is_owner = project.owner_id == user.id
    sealed = is_sealed_and_open(project)

    out = []
    for c, cp in rows:
        if is_admin or c.service_provider_id == user.id:
            out.append(_serialize(c, cp.company_name))
        elif is_owner:
            out.append(_serialize(c, cp.company_name, redact=sealed))
        elif c.shared_with_all and c.answer is not None:
            out.append(_serialize(c, cp.company_name))
    return out


@router.post("", response_model=ClarificationOut, status_code=201)
def ask_clarification(
    project_id: str, payload: ClarificationCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if user.role != UserRole.service_provider:
        raise HTTPException(status_code=403, detail="Only service providers can ask clarification questions.")

    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")
    # Stage 3.10: the requirement's own question rule (and, within it, the
    # offer deadline) -- the same rule the provider's page shows.
    if not questions_open(project):
        raise HTTPException(status_code=400, detail=questions_closed_reason(project))

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Enter a question.")

    clarification = Clarification(
        project_id=project_id, service_provider_id=user.id, question=question, shared_with_all=payload.shared_with_all
    )
    db.add(clarification)
    db.commit()
    db.refresh(clarification)

    owner = db.get(User, project.owner_id)
    if owner:
        notify_owner_new_clarification(owner.email, project.title, project_id)
        notify(db, owner, NotificationType.clarification_asked, link=f"/owner/projects/{project_id}", project_title=project.title)

    profile = db.get(ServiceProviderProfile, user.id)
    return _serialize(clarification, profile.company_name if profile else None)


@router.post("/{clarification_id}/answer", response_model=ClarificationOut)
def answer_clarification(
    project_id: str,
    clarification_id: str,
    payload: ClarificationAnswer,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found.")

    clarification = db.get(Clarification, clarification_id)
    if not clarification or clarification.project_id != project_id:
        raise HTTPException(status_code=404, detail="Question not found.")
    if clarification.answer is not None:
        raise HTTPException(status_code=400, detail="This question has already been answered.")
    # Stage 3.10: at the question cut-off the Q&A closes for both sides --
    # no new questions and no new answers -- so every provider prices
    # against the same, final set of clarifications.
    if not questions_open(project):
        raise HTTPException(status_code=400, detail="Questions and answers for this requirement have closed.")

    answer = payload.answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Enter an answer.")

    clarification.answer = answer
    clarification.answered_at = datetime.utcnow()
    db.commit()
    db.refresh(clarification)

    service_provider_user = db.get(User, clarification.service_provider_id)
    if service_provider_user:
        notify_clarification_answered(service_provider_user.email, project.title, project_id)
        notify(
            db,
            service_provider_user,
            NotificationType.clarification_answered,
            link=f"/service-provider/projects/{project_id}/offer",
            project_title=project.title,
        )

    profile = db.get(ServiceProviderProfile, clarification.service_provider_id)
    return _serialize(clarification, profile.company_name if profile else None, redact=is_sealed_and_open(project))
