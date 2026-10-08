"""Stage 7.3: the agreement governing an awarded requirement.

One agreement per award (models.agreement), created with the award. Its
parties, value, winning offer and scope version are the award record's. The
parties agree outside U-Tender and attach the signed papers here; the owner
side records when it takes effect and, if it ends early, that it was
terminated. Read by the requirement's owner side, the winning provider's side
and admins (the award's own audience); everyone else gets a 404, whatever id
they send. Completion, payments and variations are later stages."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.models.agreement import AGREEMENT_DOCUMENT_KINDS, EVIDENCE_KINDS, Agreement, AgreementDocument, ExecutionUpdate, Milestone, Variation
from app.models.award_record import AwardRecord
from app.models.common import gen_uuid
from app.models.enums import NotificationType, ProjectStatus, UserRole
from app.models.offer import Offer
from app.models.organization import Organization
from app.models.project import Project, ProjectItem
from app.models.service_provider import ServiceProviderProfile
from app.models.user import User
from app.routers.owner import _best_effort
from app.schemas.agreement import AgreementDocumentOut, AgreementOut, AgreementTerminate, AgreementUpdate, ExecutionProgress, ExecutionUpdateOut, MilestoneOut, VariationOut, WorkStart
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
            detail="This agreement was changed by someone else (the other party, a colleague or another tab) while you had it open. This page now shows the latest. Check it, then try again if still needed.",
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
    milestones = db.query(Milestone).filter(Milestone.agreement_id == agreement.id).order_by(Milestone.position.asc()).all()
    titles = {m.id: m.title for m in milestones}
    variations = db.query(Variation).filter(Variation.agreement_id == agreement.id).order_by(Variation.number.asc()).all()
    numbers = {v.id: v.number for v in variations}
    original_completion, completion_source = planned_completion(project, winner)
    current_amount, current_completion = current_terms(award, original_completion, variations)
    items = {i.id: i for i in db.query(ProjectItem).filter(ProjectItem.project_id == project.id)} if any(m.project_item_id for m in milestones) else {}
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
        completion_status=agreement.completion_status,
        completion_submitted_at=agreement.completion_submitted_at,
        completion_note=agreement.completion_note,
        completion_decided_at=agreement.completion_decided_at,
        completion_decision_note=agreement.completion_decision_note,
        outstanding_deliverables=sum(1 for m in milestones if m.status != "accepted"),
        on_hold_since=agreement.on_hold_at if agreement.status != "terminated" else None,
        execution_history=[
            ExecutionUpdateOut(
                id=u.id, sequence=u.sequence, kind=u.kind, party=u.party, note=u.note, created_at=u.created_at,
                recorded_by_name=_name(db, u.recorded_by, names) if side in (u.party, "admin") else None,
                milestone_id=u.milestone_id, milestone_title=titles.get(u.milestone_id),
            )
            for u in db.query(ExecutionUpdate).filter(ExecutionUpdate.agreement_id == agreement.id).order_by(ExecutionUpdate.sequence.asc())
        ],
        milestones=[_milestone_out(m, items, numbers) for m in milestones],
        original_amount=award.amount,
        current_amount=current_amount,
        original_completion_date=original_completion,
        original_completion_source=completion_source,
        current_completion_date=current_completion,
        variations=[_variation_out(v, titles) for v in variations],
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
                uploaded_by_name=_uploader(db, d, side, names), milestone_id=d.milestone_id, variation_id=d.variation_id, execution_update_id=d.execution_update_id,
                evidence=d.kind in EVIDENCE_KINDS or bool(d.milestone_id or d.execution_update_id),
                url=_api(f"/projects/{project.id}/agreement/documents/{d.id}/file"),
            )
            for d in docs
        ],
    )


def _milestone_out(m: Milestone, items: dict, numbers: dict) -> MilestoneOut:
    item = items.get(m.project_item_id) if m.project_item_id else None
    return MilestoneOut(
        id=m.id, position=m.position, title=m.title, description=m.description, due_date=m.due_date,
        project_item_id=m.project_item_id, project_item_label=f"{item.position}. {item.description}" if item else None,
        status=m.status, delivered_at=m.delivered_at, delivery_note=m.delivery_note,
        decided_at=m.decided_at, decision_note=m.decision_note, version=m.version,
        variation_number=numbers.get(m.variation_id) if m.variation_id else None,
    )


def _variation_out(v: Variation, titles: dict) -> VariationOut:
    return VariationOut(
        id=v.id, number=v.number, status=v.status, description=v.description, value_change=v.value_change,
        completion_date=v.completion_date, milestone_id=v.milestone_id, milestone_title=titles.get(v.milestone_id),
        milestone_due_date=v.milestone_due_date, add_deliverable=v.add_deliverable,
        proposed_party=v.proposed_party, proposed_at=v.proposed_at, decided_party=v.decided_party, decided_at=v.decided_at,
        decision_note=v.decision_note, previous_amount=v.previous_amount, resulting_amount=v.resulting_amount,
        previous_completion_date=v.previous_completion_date, previous_milestone_due_date=v.previous_milestone_due_date,
        version=v.version,
    )


def planned_completion(project: Project, winner: Offer | None):
    """Stage 7.8: the originally planned completion -- the winning offer's own
    commitment, else the requirement's expected completion."""
    def finish(completion, start, days):
        return completion or (start + timedelta(days=days) if start and days else None)

    if winner:
        when = finish(winner.proposed_completion_date, winner.proposed_start_date, winner.proposed_duration_days)
        if when:
            return when, "offer"
    when = finish(project.expected_completion_date, project.expected_start_date, project.expected_duration_days)
    return (when, "requirement") if when else (None, None)


def current_terms(award: AwardRecord, original_completion, variations):
    """Stage 7.8: the current agreed value and completion -- the original award
    plus each agreed variation, in order. Never stored over the original."""
    amount, completion = award.amount, original_completion
    for v in variations:
        if v.status == "agreed":
            amount += v.value_change or 0
            completion = v.completion_date or completion
    return amount, completion


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
    if agreement.work_started_at is None:
        return "not_started"
    if agreement.completion_status == "accepted":  # Stage 7.10: the work is done and accepted
        return "accepted"
    return "on_hold" if agreement.on_hold_at else "in_progress"


def _record(db: Session, agreement: Agreement, kind: str, side: str, user: User, note: str | None, at: datetime, milestone_id: str | None = None) -> None:
    """Stage 7.6: the next entry in the execution history -- numbered under the
    requirement's lock the caller holds."""
    last = db.query(ExecutionUpdate.sequence).filter(ExecutionUpdate.agreement_id == agreement.id).order_by(ExecutionUpdate.sequence.desc()).first()
    db.add(ExecutionUpdate(agreement_id=agreement.id, sequence=(last[0] if last else 0) + 1, kind=kind, party=side, recorded_by=user.id, note=note, created_at=at, milestone_id=milestone_id))


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
        raise HTTPException(status_code=400, detail="This agreement is no longer being prepared, so its details can't be changed. This page now shows the latest.")
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
        raise HTTPException(status_code=400, detail="This agreement is already in force or was terminated meanwhile. This page now shows the latest.")
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
        raise HTTPException(status_code=400, detail="This agreement was already terminated. This page now shows the latest.")
    if agreement.completion_status == "accepted":  # Stage 7.10
        raise HTTPException(status_code=409, detail="The work was already accepted as complete, so the agreement can't be terminated. This page now shows the latest.")
    _check_version(agreement, if_match)
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Give the reason the agreement was terminated.")
    previous = agreement.status
    agreement.status, agreement.terminated_at, agreement.termination_reason = "terminated", datetime.utcnow().replace(microsecond=0), reason
    # Stage 7.8: an open proposal can no longer be agreed; it lapses (never silently agreed).
    for v in db.query(Variation).filter(Variation.agreement_id == agreement.id, Variation.status == "proposed"):
        v.status, v.version = "lapsed", v.version + 1
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
        raise HTTPException(status_code=400, detail="This agreement has been terminated. This page now shows the latest.")
    if agreement.work_started_at is not None:
        raise HTTPException(status_code=400, detail="The start of the work was already recorded (by the other party, a colleague or another tab). This page now shows the latest.")
    _check_version(agreement, if_match)
    agreement.work_started_at = datetime.utcnow().replace(microsecond=0)
    agreement.work_started_party, agreement.work_started_by = side, user.id
    agreement.work_start_note = (payload.note or "").strip() or None
    _record(db, agreement, "started", side, user, agreement.work_start_note, agreement.work_started_at)
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


@router.post("/progress", response_model=AgreementOut)
def record_progress(
    project_id: str, payload: ExecutionProgress, if_match: str | None = Header(None, alias="If-Match"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Stage 7.6: either party, once the work has started and while the
    agreement stands, records a short progress note, puts the work on hold,
    or resumes it. The award, the winning offer and the requirement never
    change. Putting on hold and resuming tell the other party."""
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    if agreement.status == "terminated":
        raise HTTPException(status_code=400, detail="This agreement has been terminated. This page now shows the latest.")
    if agreement.work_started_at is None:
        raise HTTPException(status_code=400, detail="The work hasn't started yet. Record its start first.")
    if agreement.completion_status == "accepted":  # Stage 7.10
        raise HTTPException(status_code=409, detail="The work was already accepted as complete. This page now shows the latest.")
    if agreement.completion_status == "submitted" and payload.action != "update":
        raise HTTPException(status_code=409, detail="The work was submitted as complete and is awaiting the owner's review. This page now shows the latest.")
    note = (payload.note or "").strip() or None
    if payload.action == "update" and not note:
        raise HTTPException(status_code=400, detail="Write a short progress note.")
    if payload.action == "hold" and agreement.on_hold_at is not None:
        raise HTTPException(status_code=400, detail="The work was already put on hold (by the other party, a colleague or another tab). This page now shows the latest.")
    if payload.action == "resume" and agreement.on_hold_at is None:
        raise HTTPException(status_code=400, detail="The work isn't on hold any more: it was already resumed. This page now shows the latest.")
    _check_version(agreement, if_match)
    now = datetime.utcnow().replace(microsecond=0)
    before = _execution_status(agreement)
    if payload.action == "hold":
        agreement.on_hold_at = now
    elif payload.action == "resume":
        agreement.on_hold_at = None
    kind = {"update": "progress", "hold": "on_hold", "resume": "resumed"}[payload.action]
    _record(db, agreement, kind, side, user, note, now)
    _touch(agreement, user)
    # log_action commits: the change, its history entry and the audit row land together.
    log_action(db, actor_id=user.id, action=f"agreement.execution_{kind}", target_type="agreement", target_id=agreement.id,
               previous_value=before, new_value=_execution_status(agreement), reason=note)

    if payload.action != "update":
        state, state_ar = ("put on hold", "تم إيقاف") if payload.action == "hold" else ("resumed", "تم استئناف")

        def tell():
            if side == "owner":
                notify_team(db, db.get(User, winner.service_provider_id), NotificationType.execution_updated,
                            link=f"/service-provider/projects/{project_id}/offer", organization_id=winner.organization_id,
                            project_title=project.title, state=state, state_ar=state_ar)
            else:
                notify_team(db, db.get(User, project.owner_id), NotificationType.execution_updated,
                            link=f"/owner/projects/{project_id}", organization_id=project.organization_id,
                            project_title=project.title, state=state, state_ar=state_ar)

        _best_effort(db, tell, f"execution notifications for {project_id}")
    db.refresh(agreement)
    return _out(db, project, agreement, award, winner, side)


@router.post("/documents", response_model=AgreementOut)
async def attach_agreement_document(
    project_id: str, kind: str = Form(...), file: UploadFile = File(...), milestone_id: str | None = Form(None), variation_id: str | None = Form(None),
    execution_update_id: str | None = Form(None),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """Either party attaches a paper of the agreement -- the signed agreement,
    a work or purchase order, the final quotation, the agreed scope -- or,
    once the work has started, execution evidence (Stage 7.9): photographs,
    site, delivery, completion and inspection reports, test results. A
    document may belong to one deliverable, one variation or one progress
    update of this agreement -- never two, never another agreement's."""
    if kind not in AGREEMENT_DOCUMENT_KINDS:
        raise HTTPException(status_code=400, detail="Choose what kind of document this is.")
    milestone_id, variation_id, execution_update_id = milestone_id or None, variation_id or None, execution_update_id or None
    if sum(x is not None for x in (milestone_id, variation_id, execution_update_id)) > 1:
        raise HTTPException(status_code=400, detail="A document can relate to one deliverable, change or progress update, not several.")
    assert_allowed_extension(file.filename, ALLOWED_DRAWING_EXTENSIONS - {"zip"})
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="No file provided.")
    project, agreement, award, winner, side = _load(db, project_id, user, lock=True)
    if agreement.status == "terminated":
        raise HTTPException(status_code=400, detail="This agreement has been terminated. This page now shows the latest.")
    if milestone_id:  # Stage 7.7: evidence for one of this agreement's own deliverables
        milestone = db.get(Milestone, milestone_id)
        if not milestone or milestone.agreement_id != agreement.id:
            raise HTTPException(status_code=404, detail="Deliverable not found.")
        if milestone.status == "accepted":
            raise HTTPException(status_code=400, detail="This deliverable was already accepted. This page now shows the latest.")
    if variation_id:  # Stage 7.8: a paper of one of this agreement's own variations
        variation = db.get(Variation, variation_id)
        if not variation or variation.agreement_id != agreement.id:
            raise HTTPException(status_code=404, detail="Change not found.")
    if execution_update_id:  # Stage 7.9: evidence for one of this agreement's own progress updates
        update = db.get(ExecutionUpdate, execution_update_id)
        if not update or update.agreement_id != agreement.id:
            raise HTTPException(status_code=404, detail="Progress update not found.")
    if (kind in EVIDENCE_KINDS or execution_update_id) and agreement.work_started_at is None:
        raise HTTPException(status_code=400, detail="Execution evidence can be added once the work has started.")
    storage = get_storage()
    # Stage 7.4: keyed by the document's own id, so two uploads of the same
    # name at the same moment (owner and provider, or a repeated submit) never
    # share a stored file -- removing one can't take the other's with it.
    doc_id = gen_uuid()
    path = f"{project_id}/{agreement.id}/{doc_id}/{sanitize_path_segment(file.filename)}"
    storage.save(AGREEMENT_BUCKET, path, content, file.content_type or "application/octet-stream")
    doc = AgreementDocument(id=doc_id, agreement_id=agreement.id, kind=kind, party=side, file_path=path, file_name=safe_relative_name(file.filename), uploaded_by=user.id, milestone_id=milestone_id, variation_id=variation_id, execution_update_id=execution_update_id)
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
