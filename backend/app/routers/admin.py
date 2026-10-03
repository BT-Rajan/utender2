import json
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models.audit_log import AuditLog
from app.models.award_record import AwardRecord
from app.models.cms_content import CmsContent
from app.models.contractor import ContractorProfile
from app.models.document import ContractorDocument, DocumentRequirement, OwnerDocument
from app.models.enums import DocumentStatus, Language, NotificationType, ProjectStatus, UserRole, VerificationStatus
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.payment_override import PaymentOverride
from app.models.project import Project, ProjectDrawing
from app.models.review import Review
from app.models.user import User
from app.schemas.cms import CmsContentOut, CmsContentUpsert
from app.schemas.contractor import ContractorProfileOut, ContractorProfileUpdate
from app.schemas.document import (
    ContractorDocumentOut,
    DocumentExpiryUpdate,
    DocumentRequirementCreate,
    DocumentRequirementOut,
    OwnerDocumentOut,
    ReviewDocumentDecision,
    ReviewOwnerDocumentDecision,
)
from app.schemas.owner import OwnerProfileOut
from app.services.audit import log_action
from app.services.notify import notify
from app.services.storage import get_storage
from app.services.tender_lifecycle import is_sealed_and_open, lock_project

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------- document requirements ----------

@router.get("/requirements", response_model=list[DocumentRequirementOut])
def list_requirements(db: Session = Depends(get_db)):
    return db.query(DocumentRequirement).order_by(DocumentRequirement.created_at.desc()).all()


@router.post("/requirements", response_model=DocumentRequirementOut, status_code=201)
def add_requirement(payload: DocumentRequirementCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Document name is required.")
    req = DocumentRequirement(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        is_required=payload.is_required,
        applies_to=payload.applies_to,
        created_by=admin.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


class RequirementPatch(BaseModel):
    is_required: bool | None = None
    is_active: bool | None = None


@router.patch("/requirements/{requirement_id}", response_model=DocumentRequirementOut)
def patch_requirement(
    requirement_id: str, payload: RequirementPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    req = db.get(DocumentRequirement, requirement_id)
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found.")
    # A requirement newly turning mandatory (optional -> required) changes
    # what "compliant" means — bumping effective_from lets the review UI
    # flag any already-approved document that was submitted under the old,
    # looser terms as due for a fresh look (spec §48 versioning). Toggling
    # the other direction, or is_active alone, doesn't retroactively affect
    # anyone, so it doesn't move the date.
    if payload.is_required is True and req.is_required is False:
        req.effective_from = datetime.utcnow()
        log_action(
            db,
            actor_id=admin.id,
            action="requirement.made_required",
            target_type="document_requirement",
            target_id=requirement_id,
            previous_value="False",
            new_value="True",
        )
    if payload.is_required is not None:
        req.is_required = payload.is_required
    if payload.is_active is not None:
        # Soft-remove: deactivate rather than hard-delete, so existing
        # contractor_documents rows referencing this requirement stay
        # intact for audit history.
        req.is_active = payload.is_active
    db.commit()
    db.refresh(req)
    return req


# ---------- review queue ----------

@router.get("/review/queue")
def review_queue(db: Session = Depends(get_db)):
    profiles = (
        db.query(ContractorProfile)
        .filter(
            ContractorProfile.verification_status.in_(
                [VerificationStatus.pending_review, VerificationStatus.changes_requested]
            )
        )
        .order_by(ContractorProfile.created_at.asc())
        .all()
    )
    result = []
    for cp in profiles:
        docs = (
            db.query(ContractorDocument, DocumentRequirement)
            .join(DocumentRequirement, ContractorDocument.requirement_id == DocumentRequirement.id)
            .filter(ContractorDocument.contractor_id == cp.user_id)
            .all()
        )
        expiry = 60 * 60 * 24  # admin review links: fixed 24h window, not deadline-tied like drawings
        storage = get_storage()
        result.append(
            {
                "contractor": ContractorProfileOut(**_profile_fields(cp), email=None),
                "documents": [
                    {
                        **ContractorDocumentOut(
                            id=d.id,
                            contractor_id=d.contractor_id,
                            requirement_id=d.requirement_id,
                            status=d.status,
                            admin_note=d.admin_note,
                            reviewed_at=d.reviewed_at,
                            submitted_at=d.submitted_at,
                            expires_on=d.expires_on,
                            requirement_name=r.name,
                            requirement_description=r.description,
                            requirement_is_required=r.is_required,
                            requirement_effective_from=r.effective_from,
                        ).model_dump(),
                        "url": storage.signed_url("contractor-documents", d.file_path, expiry) if d.file_path else None,
                    }
                    for d, r in docs
                ],
            }
        )
    return result


@router.post("/review/documents", response_model=ContractorDocumentOut)
def review_document(payload: ReviewDocumentDecision, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    doc = (
        db.query(ContractorDocument)
        .filter(
            ContractorDocument.contractor_id == payload.contractor_id,
            ContractorDocument.requirement_id == payload.requirement_id,
        )
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    _get_active_contractor_profile(db, payload.contractor_id)

    doc.status = payload.decision
    doc.admin_note = (payload.note or "Document rejected — please re-upload.") if payload.decision == DocumentStatus.rejected else None
    doc.reviewed_by = admin.id
    doc.reviewed_at = datetime.utcnow()
    if payload.decision == DocumentStatus.approved:
        doc.expires_on = payload.expires_on
    db.commit()

    # A single rejected document sends the whole application back to
    # "changes requested" immediately, so the contractor sees it without
    # the admin needing a separate reject-application step.
    if payload.decision == DocumentStatus.rejected:
        cp = db.get(ContractorProfile, payload.contractor_id)
        if cp:
            cp.verification_status = VerificationStatus.changes_requested
            db.commit()

    requirement = db.get(DocumentRequirement, payload.requirement_id)
    contractor_user = db.get(User, payload.contractor_id)
    if contractor_user and requirement and payload.decision in (DocumentStatus.approved, DocumentStatus.rejected):
        notification_type = (
            NotificationType.document_approved if payload.decision == DocumentStatus.approved else NotificationType.document_rejected
        )
        notify(db, contractor_user, notification_type, link="/contractor/status", requirement_name=requirement.name)

    db.refresh(doc)
    return doc


@router.patch("/documents/{document_id}/expiry", response_model=ContractorDocumentOut)
def set_document_expiry(document_id: str, payload: DocumentExpiryUpdate, db: Session = Depends(get_db)):
    doc = db.get(ContractorDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.expires_on = payload.expires_on
    db.commit()
    db.refresh(doc)
    requirement = db.get(DocumentRequirement, doc.requirement_id)
    return ContractorDocumentOut(
        id=doc.id,
        contractor_id=doc.contractor_id,
        requirement_id=doc.requirement_id,
        status=doc.status,
        admin_note=doc.admin_note,
        reviewed_at=doc.reviewed_at,
        submitted_at=doc.submitted_at,
        expires_on=doc.expires_on,
        requirement_name=requirement.name if requirement else None,
        requirement_description=requirement.description if requirement else None,
        requirement_is_required=requirement.is_required if requirement else None,
        requirement_effective_from=requirement.effective_from if requirement else None,
    )


@router.post("/review/contractors/{contractor_id}/approve", response_model=ContractorProfileOut)
def approve_contractor(contractor_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    docs = (
        db.query(ContractorDocument, DocumentRequirement)
        .join(DocumentRequirement, ContractorDocument.requirement_id == DocumentRequirement.id)
        .filter(ContractorDocument.contractor_id == contractor_id)
        .all()
    )
    # Guard: every required document must be approved before the overall
    # application can be approved. Prevents a mis-click from activating an
    # under-verified contractor.
    missing_approval = any(r.is_required and d.status != DocumentStatus.approved for d, r in docs)
    if missing_approval:
        raise HTTPException(status_code=400, detail="All required documents must be approved before approving this contractor.")

    cp = db.get(ContractorProfile, contractor_id)
    if not cp:
        raise HTTPException(status_code=404, detail="Contractor not found.")
    previous = cp.verification_status.value
    cp.verification_status = VerificationStatus.approved
    db.commit()
    db.refresh(cp)
    log_action(
        db,
        actor_id=admin.id,
        action="verification_status.set",
        target_type="contractor_profile",
        target_id=contractor_id,
        previous_value=previous,
        new_value=VerificationStatus.approved.value,
    )
    contractor_user = db.get(User, contractor_id)
    if contractor_user:
        notify(db, contractor_user, NotificationType.verification_activated, link="/contractor/dashboard")
    return cp


@router.post("/review/contractors/{contractor_id}/reject", response_model=ContractorProfileOut)
def reject_application(contractor_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cp = db.get(ContractorProfile, contractor_id)
    if not cp:
        raise HTTPException(status_code=404, detail="Contractor not found.")
    previous = cp.verification_status.value
    cp.verification_status = VerificationStatus.changes_requested
    db.commit()
    db.refresh(cp)
    log_action(
        db,
        actor_id=admin.id,
        action="verification_status.set",
        target_type="contractor_profile",
        target_id=contractor_id,
        previous_value=previous,
        new_value=VerificationStatus.changes_requested.value,
    )
    return cp


# ---------- contractor management ----------

def _get_active_contractor_profile(db: Session, contractor_id: str) -> ContractorProfile:
    """Same reasoning as _get_active_owner_profile below (defined once
    OwnerProfile existed and this mirror was written to match): the
    documented way to create an admin is to sign up as an owner OR
    contractor and flip the role column, which leaves a real
    contractor_profiles row behind for an account that's no longer a
    contractor. Every mutation below goes through this instead of a bare
    db.get(ContractorProfile, contractor_id)."""
    cp = db.get(ContractorProfile, contractor_id)
    user = db.get(User, contractor_id)
    if not cp or not user or user.role != UserRole.contractor:
        raise HTTPException(status_code=404, detail="Contractor not found.")
    return cp


@router.get("/contractors", response_model=list[ContractorProfileOut])
def list_contractors(db: Session = Depends(get_db)):
    rows = (
        db.query(ContractorProfile, User)
        .join(User, ContractorProfile.user_id == User.id)
        .filter(User.role == UserRole.contractor)
        .all()
    )
    return [ContractorProfileOut(**_profile_fields(cp), email=u.email) for cp, u in rows]


@router.get("/contractors/{contractor_id}")
def contractor_detail(contractor_id: str, db: Session = Depends(get_db)):
    cp = _get_active_contractor_profile(db, contractor_id)
    user = db.get(User, contractor_id)
    docs = (
        db.query(ContractorDocument, DocumentRequirement)
        .join(DocumentRequirement, ContractorDocument.requirement_id == DocumentRequirement.id)
        .filter(ContractorDocument.contractor_id == contractor_id)
        .all()
    )
    return {
        "contractor": ContractorProfileOut(**_profile_fields(cp), email=user.email if user else None),
        "documents": [
            ContractorDocumentOut(
                id=d.id,
                contractor_id=d.contractor_id,
                requirement_id=d.requirement_id,
                status=d.status,
                admin_note=d.admin_note,
                reviewed_at=d.reviewed_at,
                submitted_at=d.submitted_at,
                expires_on=d.expires_on,
                requirement_name=r.name,
                requirement_description=r.description,
                requirement_is_required=r.is_required,
                requirement_effective_from=r.effective_from,
            )
            for d, r in docs
        ],
    }


@router.patch("/contractors/{contractor_id}", response_model=ContractorProfileOut)
def update_contractor(contractor_id: str, payload: ContractorProfileUpdate, db: Session = Depends(get_db)):
    cp = _get_active_contractor_profile(db, contractor_id)
    if not payload.company_name.strip():
        raise HTTPException(status_code=400, detail="Company name is required.")

    cp.company_name = payload.company_name.strip()
    cp.license_number = payload.license_number or None
    cp.primary_trade = payload.primary_trade or None
    cp.service_area = payload.service_area or None
    db.commit()
    db.refresh(cp)
    user = db.get(User, contractor_id)
    return ContractorProfileOut(**_profile_fields(cp), email=user.email if user else None)


class VerificationStatusPatch(BaseModel):
    status: VerificationStatus


@router.post("/contractors/{contractor_id}/verification-status", response_model=ContractorProfileOut)
def set_verification_status(
    contractor_id: str,
    payload: VerificationStatusPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cp = _get_active_contractor_profile(db, contractor_id)
    previous = cp.verification_status.value
    cp.verification_status = payload.status
    db.commit()
    db.refresh(cp)
    log_action(
        db,
        actor_id=admin.id,
        action="verification_status.set",
        target_type="contractor_profile",
        target_id=contractor_id,
        previous_value=previous,
        new_value=payload.status.value,
    )
    return cp


class SuspendPatch(BaseModel):
    suspended: bool


@router.post("/contractors/{contractor_id}/suspend", response_model=ContractorProfileOut)
def set_suspended(
    contractor_id: str,
    payload: SuspendPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cp = _get_active_contractor_profile(db, contractor_id)
    previous = cp.is_suspended
    cp.is_suspended = payload.suspended
    db.commit()
    db.refresh(cp)
    log_action(
        db,
        actor_id=admin.id,
        action="contractor.suspend" if payload.suspended else "contractor.reactivate",
        target_type="contractor_profile",
        target_id=contractor_id,
        previous_value=str(previous),
        new_value=str(payload.suspended),
    )
    contractor_user = db.get(User, contractor_id)
    if contractor_user:
        notify(
            db,
            contractor_user,
            NotificationType.contractor_suspended if payload.suspended else NotificationType.contractor_reactivated,
            link="/contractor/dashboard",
        )
    return cp


# ---------- payment override (spec P0: admin can activate a verified
# contractor's marketplace access without a real subscription, but only
# with a recorded reason — every grant/revoke is audited) ----------

class PaymentOverrideGrant(BaseModel):
    reason: str


@router.post("/contractors/{contractor_id}/payment-override", response_model=ContractorProfileOut)
def grant_payment_override(
    contractor_id: str,
    payload: PaymentOverrideGrant,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required to grant a payment override.")

    cp = _get_active_contractor_profile(db, contractor_id)

    previous = cp.payment_override_active
    db.add(PaymentOverride(contractor_id=contractor_id, granted_by=admin.id, reason=reason))
    cp.payment_override_active = True
    db.commit()
    db.refresh(cp)

    log_action(
        db,
        actor_id=admin.id,
        action="payment_override.grant",
        target_type="contractor_profile",
        target_id=contractor_id,
        previous_value=str(previous),
        new_value="True",
        reason=reason,
    )

    user = db.get(User, contractor_id)
    if user:
        notify(db, user, NotificationType.payment_override_granted, link="/contractor/dashboard")
    return ContractorProfileOut(**_profile_fields(cp), email=user.email if user else None)


class PaymentOverrideRevoke(BaseModel):
    reason: str | None = None


@router.post("/contractors/{contractor_id}/payment-override/revoke", response_model=ContractorProfileOut)
def revoke_payment_override(
    contractor_id: str,
    payload: PaymentOverrideRevoke,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cp = _get_active_contractor_profile(db, contractor_id)

    previous = cp.payment_override_active
    active = (
        db.query(PaymentOverride)
        .filter(PaymentOverride.contractor_id == contractor_id, PaymentOverride.revoked_at.is_(None))
        .order_by(PaymentOverride.created_at.desc())
        .first()
    )
    if active:
        active.revoked_by = admin.id
        active.revoked_at = datetime.utcnow()
    cp.payment_override_active = False
    db.commit()
    db.refresh(cp)

    log_action(
        db,
        actor_id=admin.id,
        action="payment_override.revoke",
        target_type="contractor_profile",
        target_id=contractor_id,
        previous_value=str(previous),
        new_value="False",
        reason=payload.reason,
    )

    user = db.get(User, contractor_id)
    if user:
        notify(db, user, NotificationType.payment_override_revoked, link="/contractor/dashboard")
    return ContractorProfileOut(**_profile_fields(cp), email=user.email if user else None)


@router.get("/contractors/{contractor_id}/payment-overrides")
def list_payment_overrides(contractor_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(PaymentOverride)
        .filter(PaymentOverride.contractor_id == contractor_id)
        .order_by(PaymentOverride.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "granted_by": r.granted_by,
            "reason": r.reason,
            "created_at": r.created_at,
            "revoked_by": r.revoked_by,
            "revoked_at": r.revoked_at,
        }
        for r in rows
    ]


@router.get("/contractors/{contractor_id}/audit-log")
def contractor_audit_log(contractor_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == "contractor_profile", AuditLog.target_id == contractor_id)
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "actor_id": r.actor_id,
            "action": r.action,
            "previous_value": r.previous_value,
            "new_value": r.new_value,
            "reason": r.reason,
            "created_at": r.created_at,
        }
        for r in rows
    ]


# ---------- public-site CMS (spec §14, §2.9) ----------

class CmsEntry(BaseModel):
    key: str
    en: str
    ar: str


@router.get("/cms", response_model=list[CmsEntry])
def list_cms(db: Session = Depends(get_db)):
    from app.routers.public import DEFAULT_CMS

    keys = set(DEFAULT_CMS.keys()) | {row.key for row in db.query(CmsContent.key).distinct().all()}
    overrides = {(row.key, row.language): row.value for row in db.query(CmsContent).all()}

    def resolve(key: str, lang: Language) -> str:
        if (key, lang) in overrides:
            return overrides[(key, lang)]
        return DEFAULT_CMS.get(key, {}).get(lang.value, "")

    return [CmsEntry(key=k, en=resolve(k, Language.en), ar=resolve(k, Language.ar)) for k in sorted(keys)]


@router.put("/cms/{key}/{language}", response_model=CmsContentOut)
def upsert_cms(
    key: str, language: Language, payload: CmsContentUpsert, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    row = db.query(CmsContent).filter(CmsContent.key == key, CmsContent.language == language).first()
    previous = row.value if row else None
    if row:
        row.value = payload.value
    else:
        row = CmsContent(key=key, language=language, value=payload.value)
        db.add(row)
    db.commit()
    db.refresh(row)

    log_action(
        db,
        actor_id=admin.id,
        action="cms.update",
        target_type="cms_content",
        target_id=f"{key}:{language.value}",
        previous_value=previous,
        new_value=payload.value,
    )
    return row


@router.delete("/cms/{key}/{language}", status_code=204)
def reset_cms(key: str, language: Language, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Removes an admin override, reverting the public site back to the
    built-in default copy for this key/language."""
    row = db.query(CmsContent).filter(CmsContent.key == key, CmsContent.language == language).first()
    if row:
        previous_value = row.value
        db.delete(row)
        db.commit()
        log_action(
            db,
            actor_id=admin.id,
            action="cms.reset",
            target_type="cms_content",
            target_id=f"{key}:{language.value}",
            previous_value=previous_value,
            new_value=None,
        )
    return None


# Permanently removes the contractor's account, which cascades through
# contractor_profiles → contractor_documents/offers via FK ON DELETE
# CASCADE. Blocked if the contractor has any reviews on record — those are
# part of the platform's public reputation history and reviews.contractor_id
# has no cascade by design, so a hard delete would otherwise violate that
# foreign key. Suspend instead to preserve history while cutting access.
@router.delete("/contractors/{contractor_id}", status_code=204)
def delete_contractor(contractor_id: str, db: Session = Depends(get_db)):
    _get_active_contractor_profile(db, contractor_id)  # 404s outright for a since-promoted admin account

    review_count = db.query(Review).filter(Review.contractor_id == contractor_id).count()
    if review_count > 0:
        raise HTTPException(
            status_code=400,
            detail="This contractor has completed projects with reviews on record. Suspend the account instead of deleting it, to keep that history intact.",
        )

    docs_with_files = (
        db.query(ContractorDocument.file_path)
        .filter(ContractorDocument.contractor_id == contractor_id, ContractorDocument.file_path.isnot(None))
        .all()
    )
    paths = [p[0] for p in docs_with_files if p[0]]
    if paths:
        get_storage().delete("contractor-documents", paths)

    user = db.get(User, contractor_id)
    if not user:
        raise HTTPException(status_code=404, detail="Contractor not found.")
    db.delete(user)  # cascades to contractor_profiles -> contractor_documents/offers
    db.commit()
    return None


# ---------- owner management (mirrors the contractor management section
# above: list/detail, document review, verification approve/reject,
# suspend, delete) ----------

def _owner_fields(op: OwnerProfile, user: User | None) -> dict:
    return dict(
        user_id=op.user_id,
        verification_status=op.verification_status,
        is_suspended=op.is_suspended,
        marketplace_status=op.marketplace_status,
        created_at=op.created_at,
        email=user.email if user else None,
        full_name=user.full_name if user else None,
    )


def _get_active_owner_profile(db: Session, owner_id: str) -> OwnerProfile:
    """Looks up an OwnerProfile, but only for a user whose CURRENT role is
    still owner (see list_owners' comment above for why this matters: an
    admin created via the documented "sign up as owner, flip the role"
    path still has a real owner_profiles row underneath). Every owner
    mutation endpoint below goes through this rather than a bare
    db.get(OwnerProfile, owner_id), so none of them can act on a
    since-promoted account."""
    op = db.get(OwnerProfile, owner_id)
    user = db.get(User, owner_id)
    if not op or not user or user.role != UserRole.owner:
        raise HTTPException(status_code=404, detail="Owner not found.")
    return op


def _owner_documents(db: Session, owner_id: str) -> list[OwnerDocumentOut]:
    rows = (
        db.query(OwnerDocument, DocumentRequirement)
        .join(DocumentRequirement, OwnerDocument.requirement_id == DocumentRequirement.id)
        .filter(OwnerDocument.owner_id == owner_id)
        .all()
    )
    return [
        OwnerDocumentOut(
            id=d.id,
            owner_id=d.owner_id,
            requirement_id=d.requirement_id,
            status=d.status,
            admin_note=d.admin_note,
            reviewed_at=d.reviewed_at,
            submitted_at=d.submitted_at,
            expires_on=d.expires_on,
            requirement_name=r.name,
            requirement_description=r.description,
            requirement_is_required=r.is_required,
            requirement_effective_from=r.effective_from,
        )
        for d, r in rows
    ]


@router.get("/owners", response_model=list[OwnerProfileOut])
def list_owners(db: Session = Depends(get_db)):
    # Filtered to users whose CURRENT role is still owner: the documented
    # way to create an admin account is to sign up as an owner (or
    # contractor) and flip that row's role in the database (see README's
    # "Create your first admin"), which leaves a real owner_profiles row
    # behind for an account that is no longer an owner. Without this
    # filter, every admin created that way would show up in this list and
    # be manageable as if they were a property owner.
    rows = (
        db.query(OwnerProfile, User)
        .join(User, OwnerProfile.user_id == User.id)
        .filter(User.role == UserRole.owner)
        .all()
    )
    project_counts = dict(db.query(Project.owner_id, func.count(Project.id)).group_by(Project.owner_id).all())
    return [
        OwnerProfileOut(**_owner_fields(op, u), project_count=project_counts.get(op.user_id, 0)) for op, u in rows
    ]


@router.get("/owners/{owner_id}")
def owner_detail(owner_id: str, db: Session = Depends(get_db)):
    op = db.get(OwnerProfile, owner_id)
    user = db.get(User, owner_id)
    if not op or not user or user.role != UserRole.owner:
        raise HTTPException(status_code=404, detail="Owner not found.")
    project_count = db.query(Project).filter(Project.owner_id == owner_id).count()
    return {
        "owner": OwnerProfileOut(**_owner_fields(op, user), project_count=project_count),
        "documents": _owner_documents(db, owner_id),
    }


@router.post("/review/owner-documents", response_model=OwnerDocumentOut)
def review_owner_document(
    payload: ReviewOwnerDocumentDecision, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    doc = (
        db.query(OwnerDocument)
        .filter(OwnerDocument.owner_id == payload.owner_id, OwnerDocument.requirement_id == payload.requirement_id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    _get_active_owner_profile(db, payload.owner_id)

    doc.status = payload.decision
    doc.admin_note = (payload.note or "Document rejected — please re-upload.") if payload.decision == DocumentStatus.rejected else None
    doc.reviewed_by = admin.id
    doc.reviewed_at = datetime.utcnow()
    if payload.decision == DocumentStatus.approved:
        doc.expires_on = payload.expires_on
    db.commit()

    if payload.decision == DocumentStatus.rejected:
        op = db.get(OwnerProfile, payload.owner_id)
        if op:
            op.verification_status = VerificationStatus.changes_requested
            db.commit()

    requirement = db.get(DocumentRequirement, payload.requirement_id)
    owner_user = db.get(User, payload.owner_id)
    if owner_user and requirement and payload.decision in (DocumentStatus.approved, DocumentStatus.rejected):
        notification_type = (
            NotificationType.owner_document_approved
            if payload.decision == DocumentStatus.approved
            else NotificationType.owner_document_rejected
        )
        notify(db, owner_user, notification_type, link="/owner/status", requirement_name=requirement.name)

    db.refresh(doc)
    return doc


@router.post("/review/owners/{owner_id}/approve", response_model=OwnerProfileOut)
def approve_owner(owner_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    op = _get_active_owner_profile(db, owner_id)

    docs = (
        db.query(OwnerDocument, DocumentRequirement)
        .join(DocumentRequirement, OwnerDocument.requirement_id == DocumentRequirement.id)
        .filter(OwnerDocument.owner_id == owner_id)
        .all()
    )
    missing_approval = any(r.is_required and d.status != DocumentStatus.approved for d, r in docs)
    if missing_approval:
        raise HTTPException(status_code=400, detail="All required documents must be approved before approving this owner.")

    previous = op.verification_status.value
    op.verification_status = VerificationStatus.approved
    db.commit()
    db.refresh(op)
    log_action(
        db,
        actor_id=admin.id,
        action="owner_verification_status.set",
        target_type="owner_profile",
        target_id=owner_id,
        previous_value=previous,
        new_value=VerificationStatus.approved.value,
    )
    owner_user = db.get(User, owner_id)
    if owner_user:
        notify(db, owner_user, NotificationType.owner_verification_activated, link="/owner/dashboard")
    return OwnerProfileOut(**_owner_fields(op, owner_user))


@router.post("/review/owners/{owner_id}/reject", response_model=OwnerProfileOut)
def reject_owner_application(owner_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    op = _get_active_owner_profile(db, owner_id)
    previous = op.verification_status.value
    op.verification_status = VerificationStatus.changes_requested
    db.commit()
    db.refresh(op)
    log_action(
        db,
        actor_id=admin.id,
        action="owner_verification_status.set",
        target_type="owner_profile",
        target_id=owner_id,
        previous_value=previous,
        new_value=VerificationStatus.changes_requested.value,
    )
    user = db.get(User, owner_id)
    return OwnerProfileOut(**_owner_fields(op, user))


class OwnerSuspendPatch(BaseModel):
    suspended: bool


@router.post("/owners/{owner_id}/suspend", response_model=OwnerProfileOut)
def set_owner_suspended(
    owner_id: str, payload: OwnerSuspendPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    op = _get_active_owner_profile(db, owner_id)
    previous = op.is_suspended
    op.is_suspended = payload.suspended
    db.commit()
    db.refresh(op)
    log_action(
        db,
        actor_id=admin.id,
        action="owner.suspend" if payload.suspended else "owner.reactivate",
        target_type="owner_profile",
        target_id=owner_id,
        previous_value=str(previous),
        new_value=str(payload.suspended),
    )
    owner_user = db.get(User, owner_id)
    if owner_user:
        notify(
            db,
            owner_user,
            NotificationType.owner_suspended if payload.suspended else NotificationType.owner_reactivated,
            link="/owner/dashboard",
        )
    return OwnerProfileOut(**_owner_fields(op, owner_user))


# Permanently removes the owner's account. Unlike delete_contractor
# (which only cascades to that contractor's own documents/offers —
# projects and other bidders' data are untouched), projects.owner_id has
# ON DELETE CASCADE: deleting an owner would silently wipe every project
# they ever posted, including drawings, clarifications, and every
# CONTRACTOR'S offers/reviews on those projects — data that belongs to
# other users, not just this owner. That blast radius is too large for a
# routine "remove this account" action, so deletion is blocked outright
# once the owner has posted anything; suspend instead.
@router.delete("/owners/{owner_id}", status_code=204)
def delete_owner(owner_id: str, db: Session = Depends(get_db)):
    _get_active_owner_profile(db, owner_id)  # 404s outright for a since-promoted admin account

    project_count = db.query(Project).filter(Project.owner_id == owner_id).count()
    if project_count > 0:
        raise HTTPException(
            status_code=400,
            detail="This owner has posted projects. Suspend the account instead of deleting it, to keep that project and offer history intact for the contractors involved.",
        )

    docs_with_files = (
        db.query(OwnerDocument.file_path)
        .filter(OwnerDocument.owner_id == owner_id, OwnerDocument.file_path.isnot(None))
        .all()
    )
    paths = [p[0] for p in docs_with_files if p[0]]
    if paths:
        get_storage().delete("owner-documents", paths)

    user = db.get(User, owner_id)
    if not user:
        raise HTTPException(status_code=404, detail="Owner not found.")
    db.delete(user)  # cascades to owner_profiles -> owner_documents
    db.commit()
    return None


# ---------- all offers, across every project (platform-wide operational
# visibility for admins) — unlike the owner-facing endpoint this doesn't
# redact sealed-and-still-open bids: the sealed-tender rule exists to stop
# the AWARDING party from favoring a bidder they recognize, a concern that
# doesn't apply to the platform operator, who can already see the award
# record and audit log for any project regardless of seal status. ----------

@router.get("/offers")
def list_all_offers(db: Session = Depends(get_db)):
    rows = (
        db.query(Offer, Project, ContractorProfile)
        .join(Project, Offer.project_id == Project.id)
        .outerjoin(ContractorProfile, Offer.contractor_id == ContractorProfile.user_id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    return [
        {
            "id": o.id,
            "project_id": p.id,
            "project_title": p.title,
            "project_status": p.status,
            "tender_type": p.tender_type,
            "contractor_id": o.contractor_id,
            "contractor_company_name": cp.company_name if cp else None,
            "amount": str(o.amount) if o.amount is not None else None,
            "timeline_estimate": o.timeline_estimate,
            "status": o.status,
            "revision": o.revision,
            "is_suspended": o.is_suspended,
            "message": o.message,
            "created_at": o.created_at,
            "updated_at": o.updated_at,
        }
        for o, p, cp in rows
    ]


# ---------- project & offer moderation (admin edit/suspend/delete over
# any owner's projects and any contractor's offers on them, per the same
# platform-wide oversight rationale as /admin/offers above) ----------

def _project_admin_fields(p: Project, owner: User | None) -> dict:
    return {
        "id": p.id,
        "owner_id": p.owner_id,
        "owner_name": owner.full_name if owner else None,
        "owner_email": owner.email if owner else None,
        "title": p.title,
        "address": p.address,
        "description": p.description,
        "trade": p.trade,
        "bid_deadline": p.bid_deadline,
        "status": p.status,
        "tender_type": p.tender_type,
        "tender_type_locked": p.tender_type_locked,
        "is_suspended": p.is_suspended,
        "created_at": p.created_at,
    }


def _offer_admin_fields(o: Offer, p: Project | None, cp: ContractorProfile | None) -> dict:
    return {
        "id": o.id,
        "project_id": o.project_id,
        "project_title": p.title if p else None,
        "project_status": p.status if p else None,
        "tender_type": p.tender_type if p else None,
        "contractor_id": o.contractor_id,
        "contractor_company_name": cp.company_name if cp else None,
        "amount": str(o.amount) if o.amount is not None else None,
        "timeline_estimate": o.timeline_estimate,
        "message": o.message,
        "status": o.status,
        "is_suspended": o.is_suspended,
        "revision": o.revision,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


@router.get("/projects")
def list_all_projects(db: Session = Depends(get_db)):
    rows = db.query(Project, User).join(User, Project.owner_id == User.id).order_by(Project.created_at.desc()).all()
    offer_counts = dict(db.query(Offer.project_id, func.count(Offer.id)).group_by(Offer.project_id).all())
    return [{**_project_admin_fields(p, u), "offer_count": offer_counts.get(p.id, 0)} for p, u in rows]


@router.get("/owners/{owner_id}/projects")
def list_owner_projects(owner_id: str, db: Session = Depends(get_db)):
    """Every project a given owner has posted — the drill-down from the
    owner detail page into what they've actually put on the marketplace,
    each one with a link into its own offers below."""
    _get_active_owner_profile(db, owner_id)  # 404s outright for a since-promoted admin account
    owner_user = db.get(User, owner_id)
    rows = db.query(Project).filter(Project.owner_id == owner_id).order_by(Project.created_at.desc()).all()
    offer_counts = dict(db.query(Offer.project_id, func.count(Offer.id)).group_by(Offer.project_id).all())
    return [{**_project_admin_fields(p, owner_user), "offer_count": offer_counts.get(p.id, 0)} for p in rows]


@router.get("/projects/{project_id}")
def admin_project_detail(project_id: str, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    owner = db.get(User, project.owner_id)
    offer_rows = (
        db.query(Offer, ContractorProfile)
        .outerjoin(ContractorProfile, Offer.contractor_id == ContractorProfile.user_id)
        .filter(Offer.project_id == project_id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    return {
        "project": _project_admin_fields(project, owner),
        "offers": [_offer_admin_fields(o, project, cp) for o, cp in offer_rows],
    }


class AdminProjectEdit(BaseModel):
    title: str | None = None
    address: str | None = None
    description: str | None = None
    trade: str | None = None
    bid_deadline: datetime | None = None


# A direct correction tool for an admin fixing an owner's listing (a typo, a
# wrong address, a deadline that needs adjusting) — distinct from the
# owner's own PATCH /projects/{id}, which is a versioned tender amendment
# that notifies every bidder and enforces the "can't pull a deadline
# earlier once bids are locked in" rule (spec D-001). This one is a plain
# edit with an audit trail, not a new amendment record; it doesn't touch
# tender_type or status, both of which have their own dedicated,
# validated transitions elsewhere.
@router.patch("/projects/{project_id}")
def admin_edit_project(
    project_id: str, payload: AdminProjectEdit, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    changed: list[str] = []
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty.")
        if title != project.title:
            changed.append("title")
            project.title = title
    if payload.address is not None:
        address = payload.address.strip()
        if not address:
            raise HTTPException(status_code=400, detail="Address cannot be empty.")
        if address != project.address:
            changed.append("address")
            project.address = address
    if payload.description is not None and payload.description != project.description:
        changed.append("description")
        project.description = payload.description or None
    if payload.trade is not None and payload.trade != project.trade:
        changed.append("trade")
        project.trade = payload.trade or None
    if payload.bid_deadline is not None and payload.bid_deadline != project.bid_deadline:
        changed.append("bid_deadline")
        project.bid_deadline = payload.bid_deadline

    if not changed:
        raise HTTPException(status_code=400, detail="No changes were provided.")

    db.commit()
    db.refresh(project)
    log_action(
        db,
        actor_id=admin.id,
        action="project.admin_edit",
        target_type="project",
        target_id=project_id,
        new_value=", ".join(changed),
    )
    owner = db.get(User, project.owner_id)
    return _project_admin_fields(project, owner)


class ProjectSuspendPatch(BaseModel):
    suspended: bool


@router.post("/projects/{project_id}/suspend")
def suspend_project(
    project_id: str, payload: ProjectSuspendPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")
    previous = project.is_suspended
    project.is_suspended = payload.suspended
    db.commit()
    db.refresh(project)
    log_action(
        db,
        actor_id=admin.id,
        action="project.suspend" if payload.suspended else "project.reactivate",
        target_type="project",
        target_id=project_id,
        previous_value=str(previous),
        new_value=str(payload.suspended),
    )
    owner = db.get(User, project.owner_id)
    if owner:
        notify(
            db,
            owner,
            NotificationType.project_suspended if payload.suspended else NotificationType.project_reactivated,
            link=f"/owner/projects/{project_id}",
            project_title=project.title,
        )
    return _project_admin_fields(project, owner)


# Blocked outright once the project has any offers on it — deleting it
# would cascade through offers.project_id (ON DELETE CASCADE) and silently
# erase every contractor's bid history on this project, data that belongs
# to them, not just this owner. Suspend instead, same reasoning as
# delete_owner/delete_contractor above.
@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    offer_count = db.query(Offer).filter(Offer.project_id == project_id).count()
    if offer_count > 0:
        raise HTTPException(
            status_code=400,
            detail="This project has offers on it. Suspend it instead of deleting it, to keep that bid history intact for the contractors involved.",
        )

    drawing_paths = [
        d.file_path
        for d in db.query(ProjectDrawing).filter(ProjectDrawing.project_id == project_id).all()
        if d.file_path
    ]
    if drawing_paths:
        get_storage().delete("project-drawings", drawing_paths)

    snapshot = json.dumps(
        {"title": project.title, "owner_id": project.owner_id, "status": project.status.value}, default=str
    )
    db.delete(project)  # cascades to project_drawings/project_amendments; offers already guarded to zero above
    # log_action commits, so the delete and its audit row land in one transaction.
    log_action(
        db,
        actor_id=admin.id,
        action="project.admin_delete",
        target_type="project",
        target_id=project_id,
        previous_value=snapshot,
    )
    return None


class AdminOfferEdit(BaseModel):
    amount: Decimal | None = None
    timeline_estimate: str | None = None
    message: str | None = None


def _snapshot_offer_revision(db: Session, offer: Offer) -> None:
    """Same append-only trail as the contractor's own edits in
    routers/offers.py — an admin correcting a bid still leaves the pre-edit
    values recoverable in offer_revisions, never silently overwritten."""
    db.add(
        OfferRevision(
            offer_id=offer.id,
            revision_number=offer.revision,
            amount=offer.amount,
            timeline_estimate=offer.timeline_estimate,
            message=offer.message,
            status=offer.status,
        )
    )
    offer.revision += 1


@router.patch("/offers/{offer_id}")
def admin_edit_offer(
    offer_id: str, payload: AdminOfferEdit, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found.")

    # Bid integrity: a bid on a sealed tender is untouchable until the tender
    # opens, and once a tender is decided its bids are the permanent record
    # (AwardRecord.amount must keep matching the awarded offer).
    # Locked so the guards below hold for the write that follows -- an award
    # can't land between the check and the edit.
    project = lock_project(db, offer.project_id)
    if project and is_sealed_and_open(project):
        raise HTTPException(status_code=400, detail="Bids on a sealed tender can't be edited until it has opened.")
    decided = project is not None and project.status in (ProjectStatus.awarded, ProjectStatus.no_award)
    if decided or db.query(AwardRecord).filter(AwardRecord.offer_id == offer_id).first():
        raise HTTPException(
            status_code=400,
            detail="This tender has been decided, so its bids are part of the permanent record and can't be edited.",
        )

    changed: list[str] = []
    if payload.amount is not None and payload.amount != offer.amount:
        if payload.amount <= 0:
            raise HTTPException(status_code=400, detail="Enter a valid bid amount.")
        changed.append("amount")
    if payload.timeline_estimate is not None and payload.timeline_estimate != offer.timeline_estimate:
        changed.append("timeline_estimate")
    if payload.message is not None and payload.message != offer.message:
        changed.append("message")

    if not changed:
        raise HTTPException(status_code=400, detail="No changes were provided.")

    previous_values = {field: getattr(offer, field) for field in changed}
    _snapshot_offer_revision(db, offer)
    if payload.amount is not None:
        offer.amount = payload.amount
    if payload.timeline_estimate is not None:
        offer.timeline_estimate = payload.timeline_estimate or None
    if payload.message is not None:
        offer.message = payload.message or None
    offer.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(offer)

    log_action(
        db,
        actor_id=admin.id,
        action="offer.admin_edit",
        target_type="offer",
        target_id=offer_id,
        previous_value=json.dumps({k: (None if v is None else str(v)) for k, v in previous_values.items()}),
        new_value=json.dumps({field: (lambda v: None if v is None else str(v))(getattr(offer, field)) for field in changed}),
    )
    cp = db.get(ContractorProfile, offer.contractor_id)
    return _offer_admin_fields(offer, project, cp)


class OfferSuspendPatch(BaseModel):
    suspended: bool


@router.post("/offers/{offer_id}/suspend")
def suspend_offer(
    offer_id: str, payload: OfferSuspendPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found.")
    previous = offer.is_suspended
    offer.is_suspended = payload.suspended
    db.commit()
    db.refresh(offer)
    log_action(
        db,
        actor_id=admin.id,
        action="offer.suspend" if payload.suspended else "offer.reactivate",
        target_type="offer",
        target_id=offer_id,
        previous_value=str(previous),
        new_value=str(payload.suspended),
    )
    project = db.get(Project, offer.project_id)
    contractor_user = db.get(User, offer.contractor_id)
    if contractor_user and project:
        notify(
            db,
            contractor_user,
            NotificationType.offer_suspended if payload.suspended else NotificationType.offer_reactivated,
            link=f"/contractor/projects/{project.id}/offer",
            project_title=project.title,
        )
    cp = db.get(ContractorProfile, offer.contractor_id)
    return _offer_admin_fields(offer, project, cp)


# Blocked outright once the offer has been awarded — AwardRecord.offer_id
# has no cascade by design (it's a permanent record, spec §34/§87), so a
# hard delete would violate that foreign key anyway; suspend instead to
# keep the award's history intact.
@router.delete("/offers/{offer_id}", status_code=204)
def delete_offer(offer_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found.")

    awarded = db.query(AwardRecord).filter(AwardRecord.offer_id == offer_id).first()
    if awarded:
        raise HTTPException(
            status_code=400,
            detail="This offer was awarded and has a permanent award record on file. Suspend it instead of deleting it.",
        )

    snapshot = json.dumps(
        {
            "project_id": offer.project_id,
            "contractor_id": offer.contractor_id,
            "amount": str(offer.amount),
            "status": offer.status.value,
        },
        default=str,
    )
    db.delete(offer)  # cascades to offer_revisions
    log_action(
        db,
        actor_id=admin.id,
        action="offer.admin_delete",
        target_type="offer",
        target_id=offer_id,
        previous_value=snapshot,
    )
    return None


def _profile_fields(cp: ContractorProfile) -> dict:
    return dict(
        user_id=cp.user_id,
        company_name=cp.company_name,
        license_number=cp.license_number,
        primary_trade=cp.primary_trade,
        service_area=cp.service_area,
        verification_status=cp.verification_status,
        is_suspended=cp.is_suspended,
        avg_rating=cp.avg_rating,
        review_count=cp.review_count,
        subscription_status=cp.subscription_status,
        subscription_current_period_end=cp.subscription_current_period_end,
        payment_override_active=cp.payment_override_active,
        marketplace_status=cp.marketplace_status,
        created_at=cp.created_at,
    )
