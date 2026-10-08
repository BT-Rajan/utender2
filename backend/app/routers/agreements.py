"""Stage 7.3: the agreement governing an awarded requirement.

One agreement per award (models.agreement), created with the award. Its
parties, value, winning offer and scope version are the award record's. The
parties agree outside U-Tender and attach the signed papers here; the owner
side records when it takes effect and, if it ends early, that it was
terminated. Read by the requirement's owner side, the winning provider's side
and admins (the award's own audience); everyone else gets a 404, whatever id
they send. Completion, payments and variations are later stages."""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models.agreement import AGREEMENT_DOCUMENT_KINDS, Agreement, AgreementDocument
from app.models.award_record import AwardRecord
from app.models.common import gen_uuid
from app.models.enums import NotificationType, ProjectStatus, UserRole
from app.models.offer import Offer
from app.models.organization import Organization
from app.models.project import Project
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.routers.owner import _best_effort
from app.schemas.agreement import AgreementDocumentOut, AgreementOut, AgreementTerminate, AgreementUpdate, WorkStart
from app.services.audit import log_action
from app.services.notify import notify_team
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS, assert_allowed_extension, safe_relative_name, sanitize_path_segment
from app.services.offer_response import OPEN_LINK_SECONDS, _api
from app.services.storage import get_storage
from app.services.team import acting_profile, can_access, owns
from app.services.tender_lifecycle import lock_project

AGREEMENT_BUCKET = "agreement-documents"

router = APIRouter(prefix="/projects/{project_id}/agreement", tags=["agreements"])


def _side(db: Session, user: User, project: Project, winner: Offer | None) -> str | None:
    """Who the caller is to this agreement: the owner side, the winning
    provider's side, an admin -- or no one (losers, outsiders, other owners)."""
    if user.role == UserRole.admin:
        return "admin"
    if owns(db, user, project):
        return "owner"
    if (
        user.role == UserRole.service_provider
        and winner is not None
        and not project.is_suspended  # moderation pulls a suspended requirement out of providers' sight
        and can_access(db, user, winner.organization_id, winner.service_provider_id)
    ):
        profile = acting_profile(db, user)
        if not profile or profile.is_suspended:  # a suspended account loses access, as everywhere
            return None
        return "provider"
    return None


def _load(db: Session, project_id: str, user: User, *, lock: bool = False):
    project = lock_project(db, project_id) if lock else db.get(Project, project_id)
    agreement = db.query(Agreement).filter(Agreement.project_id == project_id).first() if project else None
    award = db.get(AwardRecord, agreement.award_id) if agreement else None
    winner = db.get(Offer, award.offer_id) if award else None
    side = _side(db, user, project, winner) if award and project.status == ProjectStatus.awarded else None
    if side is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    if lock:
        if agreement:
            db.refresh(agreement)
        if side == "admin":
            raise HTTPException(status_code=403, detail="Only the parties to the agreement can change it.")
        profile = acting_profile(db, user)
        if not profile or profile.verification_status.value != "approved" or profile.is_suspended:
            raise HTTPException(status_code=403, detail="not_approved")
        if project.is_suspended:
            raise HTTPException(status_code=400, detail="This requirement is suspended.")
    return project, agreement, award, winner, side


def _require_owner(side: str) -> None:
    if side != "owner":
        raise HTTPException(status_code=403, detail="Only the owner side can change the agreement's details or status.")


def _check_version(agreement: Agreement, if_match: str | None) -> None:
    if if_match and if_match.strip('"') != str(agreement.version):
        raise HTTPException(
            status_code=409,
            detail="This agreement was changed somewhere else (another tab, device or team member) since you opened it. Reload to see the latest, then make your change again.",
        )


def _touch(agreement: Agreement, user: User) -> None:
    agreement.version += 1
    agreement.updated_at, agreement.updated_by = datetime.utcnow().replace(microsecond=0), user.id


def _out(db: Session, project: Project, agreement: Agreement, award: AwardRecord, winner: Offer | None, side: str) -> AgreementOut:
    from app.routers.projects import _owner_name

    if winner and winner.organization_id:
        org = db.get(Organization, winner.organization_id)
        provider_name = org.legal_name if org else None
    else:
        cp = db.get(ServiceProviderProfile, award.service_provider_id)
        provider_name = cp.company_name if cp else None
    # Stage 7.4: who attached each paper -- the member's name for the caller's
    # own side; the other party sees which side it came from.
    names = {}
    planned, source = None, None
    if winner and winner.proposed_start_date:
        planned, source = winner.proposed_start_date, "offer"
    elif project.expected_start_date:
        planned, source = project.expected_start_date, "requirement"
    docs = db.query(AgreementDocument).filter(AgreementDocument.agreement_id == agreement.id).order_by(AgreementDocument.uploaded_at.asc(), AgreementDocument.id.asc())
    return AgreementOut(
        id=agreement.id,
        status=agreement.status,
        reference=agreement.reference,
        effective_date=agreement.effective_date,
        activated_at=agreement.activated_at,
        terminated_at=agreement.terminated_at,
        termination_reason=agreement.termination_reason,
        version=agreement.version,
        created_at=agreement.created_at,
        updated_at=agreement.updated_at,
        award_id=award.id,
        awarded_at=award.created_at,
        project_id=project.id,
        project_title=project.title,
        offer_id=award.offer_id,
        offer_revision=award.offer_revision,
        material_revision=winner.based_on_material_revision if winner else None,
        amount=award.amount,
        currency=get_settings().marketplace_currency,
        owner_name=_owner_name(db, project),
        provider_name=provider_name,
        execution_status=_execution_status(agreement),
        planned_start_date=planned,
        planned_start_source=source,
        work_started_at=agreement.work_started_at,
        work_started_party=agreement.work_started_party,
        work_started_by_name=_name(db, agreement.work_started_by, names) if side in (agreement.work_started_party, "admin") else None,
        work_start_note=agreement.work_start_note,
        side=side,
        documents=[
            AgreementDocumentOut(
                id=d.id, kind=d.kind, party=d.party, file_name=d.file_name, uploaded_at=d.uploaded_at,
                uploaded_by_name=_uploader(db, d, side, names),
                url=_api(f"/projects/{project.id}/agreement/documents/{d.id}/file"),
            )
            for d in docs
        ],
    )


def _name(db: Session, user_id: str | None, cache: dict) -> str | None:
    if not user_id:
        return None
    if user_id not in cache:
        u = db.get(User, user_id)
        cache[user_id] = (u.full_name or u.email) if u else None
    return cache[user_id]


def _uploader(db: Session, doc: AgreementDocument, side: str, cache: dict) -> str | None:
    return _name(db, doc.uploaded_by, cache) if side in (doc.party, "admin") else None


def _execution_status(agreement: Agreement) -> str:
    """Stage 7.5: derived, never stored -- so it can't disagree with the agreement."""
    if agreement.status == "terminated":
        return "terminated"
    return "in_progress" if agreement.work_started_at else "not_started"


@router.get("", response_model=AgreementOut)
def get_agreement(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    project, agreement, award, winner, side = _load(db, project_id, user)
    return _out(db, project, agreement, award, winner, side)


@router.patch("", response_model=AgreementOut)
def update_agreement(
    project_id: str, payload: AgreementUpdate, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The owner side records the parties' own reference and the date the
    agreement takes effect -- while it is being prepared."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    if agreement.status != "preparing":
        raise HTTPException(status_code=400, detail="Only an agreement being prepared can be changed.")
    _check_version(agreement, if_match)
    before = f"reference:{agreement.reference} effective:{agreement.effective_date}"
    agreement.reference = (payload.reference or "").strip() or None
    agreement.effective_date = payload.effective_date
    _touch(agreement, user)
    log_action(db, actor_id=user.id, action="agreement.update", target_type="agreement", target_id=agreement.id,
               previous_value=before, new_value=f"reference:{agreement.reference} effective:{agreement.effective_date}")
    return _out(db, project, agreement, award, winner, side)


@router.post("/activate", response_model=AgreementOut)
def activate_agreement(
    project_id: str, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The parties have agreed: the agreement is in force from its effective date."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    if agreement.status != "preparing":
        raise HTTPException(status_code=400, detail="This agreement is already in force or has been terminated.")
    _check_version(agreement, if_match)
    if agreement.effective_date is None:
        raise HTTPException(status_code=400, detail="Enter the date the agreement takes effect first.")
    agreement.status, agreement.activated_at = "active", datetime.utcnow().replace(microsecond=0)
    _touch(agreement, user)
    log_action(db, actor_id=user.id, action="agreement.activate", target_type="agreement", target_id=agreement.id,
               previous_value="preparing", new_value="active")
    return _out(db, project, agreement, award, winner, side)


@router.post("/terminate", response_model=AgreementOut)
def terminate_agreement(
    project_id: str, payload: AgreementTerminate, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """The agreement ended before the work was completed. The award stays on
    record exactly as it was made: the requirement remains awarded."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    _require_owner(side)
    if agreement.status == "terminated":
        raise HTTPException(status_code=400, detail="This agreement has already been terminated.")
    _check_version(agreement, if_match)
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Give the reason the agreement was terminated.")
    previous = agreement.status
    agreement.status, agreement.terminated_at, agreement.termination_reason = "terminated", datetime.utcnow().replace(microsecond=0), reason
    _touch(agreement, user)
    log_action(db, actor_id=user.id, action="agreement.terminate", target_type="agreement", target_id=agreement.id,
               previous_value=previous, new_value="terminated", reason=reason)
    return _out(db, project, agreement, award, winner, side)


@router.post("/start-work", response_model=AgreementOut)
def start_work(
    project_id: str, payload: WorkStart, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Stage 7.5: either party records that the awarded work has started --
    once, at the server's time. The other party is told."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    if agreement.status == "terminated":
        raise HTTPException(status_code=400, detail="This agreement has been terminated.")
    if agreement.work_started_at is not None:
        raise HTTPException(status_code=400, detail="The start of the work has already been recorded.")
    _check_version(agreement, if_match)
    agreement.work_started_at = datetime.utcnow().replace(microsecond=0)
    agreement.work_started_party, agreement.work_started_by = side, user.id
    agreement.work_start_note = (payload.note or "").strip() or None
    _touch(agreement, user)
    # log_action commits: the start and its audit entry land together.
    log_action(db, actor_id=user.id, action="agreement.start_work", target_type="agreement", target_id=agreement.id,
               previous_value="not_started", new_value="in_progress", reason=agreement.work_start_note)

    def tell():
        if side == "owner":
            first = db.get(User, winner.service_provider_id)
            notify_team(db, first, NotificationType.work_started, link=f"/service-provider/projects/{project_id}/offer",
                        organization_id=winner.organization_id, project_title=project.title)
        else:
            first = db.get(User, project.owner_id)
            notify_team(db, first, NotificationType.work_started, link=f"/owner/projects/{project_id}",
                        organization_id=project.organization_id, project_title=project.title)

    _best_effort(db, tell, f"work-started notifications for {project_id}")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/documents", response_model=AgreementOut)
async def attach_agreement_document(
    project_id: str, kind: str = Form(...), file: UploadFile = File(...),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Either party attaches a paper of the agreement -- the signed agreement,
    a work or purchase order, the final quotation, the agreed scope."""
    if kind not in AGREEMENT_DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail="Choose what kind of document this is.")
    assert_allowed_extension(file.filename, ALLOWED_DRAWING_EXTENSIONS - {"zip"})
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="No file provided.")
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    if agreement.status == "terminated":
        raise HTTPException(status_code=400, detail="This agreement has been terminated.")
    storage = get_storage()
    # Stage 7.4: keyed by the document's own id, so two uploads of the same
    # name at the same moment (owner and provider, or a repeated submit) never
    # share a stored file -- removing one can't take the other's with it.
    doc_id = gen_uuid()
    path = f"{project_id}/{agreement.id}/{doc_id}/{sanitize_path_segment(file.filename)}"
    storage.save(AGREEMENT_BUCKET, path, content, file.content_type or "application/octet-stream")
    doc = AgreementDocument(id=doc_id, agreement_id=agreement.id, kind=kind, party=side, file_path=path, file_name=safe_relative_name(file.filename), uploaded_by=user.id)
    db.add(doc)
    try:
        db.flush()
        # log_action commits: the document and its audit entry land together.
        log_action(db, actor_id=user.id, action="agreement.document_add", target_type="agreement", target_id=agreement.id, new_value=f"{doc.id}:{kind}")
    except Exception:  # never leave a stored file no record points to
        db.rollback()
        try:
            storage.delete(AGREEMENT_BUCKET, [path])
        except Exception:
            pass
        raise
    return _out(db, project, agreement, award, winner, side)


@router.delete("/documents/{document_id}", response_model=AgreementOut)
def remove_agreement_document(project_id: str, document_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A side removes a paper it attached, while the agreement is being
    prepared; once in force, its papers stay on record."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    doc = db.get(AgreementDocument, document_id)
    if not doc or doc.agreement_id != agreement.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    if doc.party != side:
        raise HTTPException(status_code=403, detail="Only the side that attached a document can remove it.")
    if agreement.status != "preparing":
        raise HTTPException(status_code=400, detail="Documents of an agreement in force or terminated stay on record.")
    path = doc.file_path
    db.delete(doc)
    log_action(db, actor_id=user.id, action="agreement.document_remove", target_type="agreement", target_id=agreement.id, previous_value=f"{document_id}:{doc.kind}")
    try:
        get_storage().delete(AGREEMENT_BUCKET, [path])
    except Exception:
        pass
    return _out(db, project, agreement, award, winner, side)


@router.get("/documents/{document_id}/file")
def open_agreement_document(project_id: str, document_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Authorised on every click, then a one-minute link."""
    _, agreement, _, _, _ = _load(db, project_id, user)
    doc = db.get(AgreementDocument, document_id)
    if not doc or doc.agreement_id != agreement.id:
        raise HTTPException(status_code=404, detail="Document not found.")
    url = get_storage().signed_url(AGREEMENT_BUCKET, doc.file_path, OPEN_LINK_SECONDS, doc.file_name)
    return RedirectResponse(url, status_code=303, headers={"Cache-Control": "no-store"})
