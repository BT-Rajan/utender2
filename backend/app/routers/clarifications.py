from datetime import datetime

import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_owner
from app.models.clarification import Clarification, ClarificationAttachment
from app.models.service_provider import ServiceProviderProfile
from app.models.enums import NotificationType, OfferStatus, UserRole
from app.models.offer import Offer, tendered
from app.models.project_amendment import ProjectAmendment
from app.models.project import Project
from app.models.user import User
from app.routers.projects import _can_view_project
from app.services.tender_rules import questions_closed_reason, questions_open
from app.schemas.clarification import ClarificationAnswer, ClarificationAttachmentOut, ClarificationCreate, ClarificationOut
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS, assert_allowed_extension, safe_relative_name, sanitize_path_segment
from app.services.storage import drawing_url_expiry_seconds, get_storage
from app.services.email import notify_clarification_answered, notify_owner_new_clarification
from app.services.notify import notify, notify_team
from app.services.audit import log_action
from app.services.team import acting_id, acting_profile, can_access, org_of, owns, side_users
from app.services.tender_lifecycle import interested_providers, is_sealed_and_open

router = APIRouter(prefix="/projects/{project_id}/clarifications", tags=["clarifications"])


def _serialize(
    db: Session, c: Clarification, company_name: str | None, redact: bool = False, mine: bool = False, owner_side: bool = False
) -> ClarificationOut:
    amendment = db.get(ProjectAmendment, c.amendment_id) if c.amendment_id else None
    answerer = db.get(User, c.answered_by) if (owner_side and c.answered_by) else None
    # Files go with what they belong to: the question's with the question; the
    # answer's once there is an answer (or to the owner side preparing it).
    storage = get_storage()
    project = db.get(Project, c.project_id)
    expiry = drawing_url_expiry_seconds(project.bid_deadline)
    files = [
        ClarificationAttachmentOut(
            id=a.id, part=a.part, file_name=a.file_name, size_bytes=a.size_bytes,
            url=storage.signed_url(CLARIFICATION_BUCKET, a.file_path, expiry, a.file_name),
        )
        # The question's files before the answer's, then in upload order -- a
        # stable order on every database (MySQL keeps whole seconds).
        for a in db.query(ClarificationAttachment).filter(ClarificationAttachment.clarification_id == c.id).order_by(
            ClarificationAttachment.part.desc(), ClarificationAttachment.created_at, ClarificationAttachment.file_name
        )
        if a.part == "question" or c.answer is not None or owner_side
    ]
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
        mine=mine,
        answered_by_name=(answerer.full_name or answerer.email) if answerer else None,
        amendment_number=amendment.amendment_number if amendment else None,
        attachments=files,
    )


# Visibility (spec §2.7, D-008): admin sees everything. A service provider always
# sees their own questions (answer pending or not, shared or private) —
# but another service provider's question is visible only once it's both
# answered AND marked shared_with_all, so an unanswered or deliberately
# private Q&A never leaks to the rest of the field. The owner sees every
# question too, EXCEPT that while the tender is sealed and still open
# (spec §19-21, D-001: bidder identity hidden from the owner until close),
# Stage 4.7: and a shared Q&A shown to OTHER providers never says who asked --
# the question and answer are for everyone; the asker's identity isn't.
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
    is_owner = owns(db, user, project)
    sealed = is_sealed_and_open(project)

    out = []
    for c, cp in rows:
        mine = can_access(db, user, c.organization_id, c.service_provider_id)
        if is_admin:
            out.append(_serialize(db, c, cp.company_name, owner_side=True))
        elif mine:  # the asker's own side
            out.append(_serialize(db, c, cp.company_name, mine=True))
        elif is_owner:
            out.append(_serialize(db, c, cp.company_name, redact=sealed, owner_side=True))
        elif c.shared_with_all and c.answer is not None:
            out.append(_serialize(db, c, None, redact=True))
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
    # Stage 4.7: the same question sent twice (a double click, a retry) is
    # one question.
    asker = acting_id(db, user)
    existing = (
        db.query(Clarification)
        .filter(Clarification.project_id == project_id, Clarification.service_provider_id == asker, Clarification.question == question, Clarification.answer.is_(None))
        .first()
    )
    if existing:
        profile = acting_profile(db, user)
        return _serialize(db, existing, profile.company_name if profile else None, mine=True)

    clarification = Clarification(
        project_id=project_id,
        service_provider_id=asker,
        organization_id=org_of(db, user.id),
        question=question,
        shared_with_all=payload.shared_with_all,
    )
    db.add(clarification)
    db.commit()
    db.refresh(clarification)

    owner = db.get(User, project.owner_id)
    if owner:
        notify_owner_new_clarification(owner.email, project.title, project_id)
        notify_team(db, owner, NotificationType.clarification_asked, link=f"/owner/projects/{project_id}", organization_id=project.organization_id, project_title=project.title)

    profile = acting_profile(db, user)
    return _serialize(db, clarification, profile.company_name if profile else None, mine=True)


@router.post("/{clarification_id}/answer", response_model=ClarificationOut)
def answer_clarification(
    project_id: str,
    clarification_id: str,
    payload: ClarificationAnswer,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    project = db.get(Project, project_id)
    if not project or not owns(db, user, project):
        raise HTTPException(status_code=404, detail="Project not found.")

    # Locked: two people on the owner's side answering at once -- one answer
    # is recorded, the other is told it was already answered.
    clarification = db.query(Clarification).filter(Clarification.id == clarification_id).populate_existing().with_for_update().first()
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
    clarification.answered_by = user.id
    # The owner may publish a privately asked question for everyone (its
    # asker stays anonymous) -- never make a shared one private.
    asked_privately = not clarification.shared_with_all
    if payload.shared_with_all:
        clarification.shared_with_all = True
    # log_action commits: the answer and its audit entry land together.
    log_action(
        db, actor_id=user.id, action="clarification.answer", target_type="clarification", target_id=clarification.id,
        previous_value="private" if asked_privately else "shared", new_value="shared" if clarification.shared_with_all else "private",
    )
    db.refresh(clarification)

    service_provider_user = db.get(User, clarification.service_provider_id)
    if service_provider_user:
        notify_clarification_answered(service_provider_user.email, project.title, project_id)
        notify_team(
            db,
            service_provider_user,
            NotificationType.clarification_answered,
            organization_id=clarification.organization_id,
            link=f"/service-provider/projects/{project_id}/offer",
            project_title=project.title,
        )

    if clarification.shared_with_all:
        _tell_the_field(db, project, clarification)

    profile = db.get(ServiceProviderProfile, clarification.service_provider_id)
    return _serialize(db, clarification, profile.company_name if profile else None, redact=is_sealed_and_open(project), owner_side=True)


def _tell_the_field(db: Session, project: Project, clarification: Clarification) -> None:
    """Stage 4.7: an answer published for everyone reaches the providers
    involved -- bidders, and those told about it or asking about it -- other
    than the asker (told separately). One notification each, de-duplicated
    by the notification system while unread."""
    link = f"/service-provider/projects/{project.id}/offer"
    asker_side = {u.id for u in side_users(db, clarification.organization_id, clarification.service_provider_id)}
    people = {}
    for provider_id, organization_id in db.query(Offer.service_provider_id, Offer.organization_id).filter(Offer.project_id == project.id, Offer.status != OfferStatus.withdrawn, tendered()).distinct():
        for u in side_users(db, organization_id, provider_id):
            people[u.id] = u
    for u in interested_providers(db, project):
        people[u.id] = u
    for uid, person in people.items():
        if uid not in asker_side:
            notify(db, person, NotificationType.clarification_shared, link=link, project_title=project.title)
    db.commit()


CLARIFICATION_BUCKET = "clarification-documents"
MAX_FILES_PER_PART = 5
ATTACHMENT_EXTENSIONS = ALLOWED_DRAWING_EXTENSIONS - {"zip"}


@router.post("/{clarification_id}/attachments", response_model=ClarificationOut)
async def attach_files(
    project_id: str,
    clarification_id: str,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stage 4.7 follow-up: files on a question (its asker's side, while it is
    unanswered) or on its answer (the owner's side) -- only while the Q&A is
    open. Kept once added: what was asked and answered stays as it was."""
    project = db.get(Project, project_id)
    if not project or not _can_view_project(user, project, db):
        raise HTTPException(status_code=404, detail="Project not found.")
    clarification = db.query(Clarification).filter(Clarification.id == clarification_id).populate_existing().with_for_update().first()
    if not clarification or clarification.project_id != project_id:
        raise HTTPException(status_code=404, detail="Question not found.")
    owner_side = owns(db, user, project)
    if owner_side:
        part = "answer"
        profile = acting_profile(db, user)
        if not profile or not profile.is_verified_active:
            raise HTTPException(status_code=403, detail="not_approved")
    elif user.role == UserRole.service_provider and can_access(db, user, clarification.organization_id, clarification.service_provider_id):
        part = "question"
        if clarification.answer is not None:
            raise HTTPException(status_code=400, detail="This question has already been answered.")
    else:
        raise HTTPException(status_code=404, detail="Question not found.")
    if not questions_open(project):
        raise HTTPException(status_code=400, detail="Questions and answers for this requirement have closed.")

    real = [f for f in files if f and f.filename]
    for f in real:
        assert_allowed_extension(f.filename, ATTACHMENT_EXTENSIONS)
    existing = db.query(ClarificationAttachment).filter(ClarificationAttachment.clarification_id == clarification.id, ClarificationAttachment.part == part).count()
    if existing + len(real) > MAX_FILES_PER_PART:
        raise HTTPException(status_code=400, detail="Attach up to 5 files to a question or an answer.")
    contents = [(f, await f.read()) for f in real]  # every file checked before any is stored
    if any(not content for _, content in contents):
        raise HTTPException(status_code=400, detail="That file is empty.")
    storage = get_storage()
    for f, content in contents:
        name = safe_relative_name(f.filename).rsplit("/", 1)[-1]
        path = f"{project_id}/{clarification.id}/{part}/{int(time.time() * 1000)}-{sanitize_path_segment(name)}"
        storage.save(CLARIFICATION_BUCKET, path, content, f.content_type or "application/octet-stream")
        db.add(ClarificationAttachment(clarification_id=clarification.id, part=part, file_path=path, file_name=name, size_bytes=len(content), uploaded_by=user.id))
    db.commit()
    db.refresh(clarification)
    asker = db.get(ServiceProviderProfile, clarification.service_provider_id)
    if owner_side:
        return _serialize(db, clarification, asker.company_name if asker else None, redact=is_sealed_and_open(project), owner_side=True)
    return _serialize(db, clarification, asker.company_name if asker else None, mine=True)
