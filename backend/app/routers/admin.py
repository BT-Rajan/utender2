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
from app.models.service_provider import ServiceProviderProfile
from app.models.document import ServiceProviderDocument, DocumentRequirement, OwnerDocument
from app.models.enums import DocumentStatus, Language, NotificationType, PricingBasis, ProjectStatus, StakeholderType, UserRole, VerificationStatus
from app.models.offer import Offer, OfferRevision
from app.models.owner import OwnerProfile
from app.models.payment_override import PaymentOverride
from app.models.project import Project, ProjectDrawing
from app.models.review import Review
from app.models.user import User
from app.schemas.cms import CmsContentOut, CmsContentUpsert
from app.schemas.service_provider import ServiceProviderProfileOut, ServiceProviderProfileUpdate
from app.schemas.document import (
    ServiceProviderDocumentOut,
    DocumentExpiryUpdate,
    DocumentRequirementCreate,
    DocumentRequirementOut,
    OwnerDocumentOut,
    ReviewDocumentDecision,
    ReviewOwnerDocumentDecision,
)
from app.schemas.owner import OwnerProfileOut
from app.schemas.common import utc_iso
from app.services.audit import log_action
from app.services.stakeholder import describe as describe_stakeholder
from app.services.verification import assert_ready_to_approve, checklist, document_out_fields, is_added_qualification, profile_state_fields
from app.services.notify import notify, notify_team
from app.services.storage import get_storage
from app.services.tender_lifecycle import is_sealed_and_open, lock_project
from app.models.category import ServiceCategory
from app.schemas.category import CategoryCreate, CategoryOut, CategoryPatch
from app.services.categories import rename_category, resolve_trade
from app.services.eligibility import ineligibility_reasons, rules_for
from app.routers.offers import _snapshot_revision
from app.schemas.offer import OfferCreate, OfferItemPrice
from app.services.offer_response import check_complete, priced_total

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------- document requirements ----------

@router.get("/requirements", response_model=list[DocumentRequirementOut])
def list_requirements(db: Session = Depends(get_db)):
    return db.query(DocumentRequirement).order_by(DocumentRequirement.created_at.desc()).all()


# ---------- Service categories (types of work) ----------


@router.get("/categories", response_model=list[CategoryOut])
def list_all_categories(db: Session = Depends(get_db)):
    return db.query(ServiceCategory).order_by(ServiceCategory.name.asc()).all()


def _name_taken(db: Session, name: str, exclude_id: str | None = None) -> bool:
    query = db.query(ServiceCategory).filter(func.lower(ServiceCategory.name) == name.lower())
    if exclude_id:
        query = query.filter(ServiceCategory.id != exclude_id)
    return query.first() is not None


@router.post("/categories", response_model=CategoryOut, status_code=201)
def add_category(payload: CategoryCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if _name_taken(db, payload.name):
        raise HTTPException(status_code=409, detail="A category with that name already exists.")
    category = ServiceCategory(name=payload.name, is_active=True)
    db.add(category)
    db.commit()
    db.refresh(category)
    log_action(db, actor_id=admin.id, action="category.created", target_type="service_category", target_id=category.id, new_value=category.name)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def edit_category(category_id: str, payload: CategoryPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Rename (requirements filed under it follow) or deactivate (no longer
    offered for new requirements or profiles; existing ones keep it)."""
    category = db.get(ServiceCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found.")
    previous = f"{category.name} ({'active' if category.is_active else 'inactive'})"
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Enter a name.")
        if _name_taken(db, name, exclude_id=category.id):
            raise HTTPException(status_code=409, detail="A category with that name already exists.")
        rename_category(db, category, name)
    if payload.is_active is not None:
        category.is_active = payload.is_active
    db.commit()
    db.refresh(category)
    log_action(
        db, actor_id=admin.id, action="category.updated", target_type="service_category", target_id=category.id,
        previous_value=previous, new_value=f"{category.name} ({'active' if category.is_active else 'inactive'})",
    )
    return category


@router.post("/requirements", response_model=DocumentRequirementOut, status_code=201)
def add_requirement(payload: DocumentRequirementCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Document name is required.")
    req = DocumentRequirement(
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        is_required=payload.is_required,
        applies_to=payload.applies_to,
        applies_to_stakeholder=payload.applies_to_stakeholder,
        requires_expiry=payload.requires_expiry,
        created_by=admin.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


class RequirementPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    is_required: bool | None = None
    is_active: bool | None = None
    # Send null explicitly to make a requirement apply to both stakeholder types.
    applies_to_stakeholder: StakeholderType | None = None
    requires_expiry: bool | None = None


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
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Document name is required.")
        if name != req.name:
            log_action(
                db,
                actor_id=admin.id,
                action="requirement.renamed",
                target_type="document_requirement",
                target_id=requirement_id,
                previous_value=req.name,
                new_value=name,
            )
            req.name = name
    if payload.description is not None:
        req.description = payload.description.strip() or None
    if "applies_to_stakeholder" in payload.model_fields_set and payload.applies_to_stakeholder != req.applies_to_stakeholder:
        log_action(
            db,
            actor_id=admin.id,
            action="requirement.scope_changed",
            target_type="document_requirement",
            target_id=requirement_id,
            previous_value=req.applies_to_stakeholder.value if req.applies_to_stakeholder else "all",
            new_value=payload.applies_to_stakeholder.value if payload.applies_to_stakeholder else "all",
        )
        req.applies_to_stakeholder = payload.applies_to_stakeholder
    if payload.requires_expiry is not None:
        req.requires_expiry = payload.requires_expiry
    if payload.is_required is not None:
        req.is_required = payload.is_required
    if payload.is_active is not None:
        # Soft-remove: deactivate rather than hard-delete, so existing
        # service_provider_documents rows referencing this requirement stay
        # intact for audit history.
        req.is_active = payload.is_active
    db.commit()
    db.refresh(req)
    return req


# ---------- review queue ----------

_ADMIN_LINK_SECONDS = 60 * 60 * 24  # admin review links: fixed 24h window, not deadline-tied like drawings


class ApplicationDecision(BaseModel):
    note: str | None = None


def _side(profile) -> tuple[str, str]:
    """(audit target_type, user-facing status link) for a profile."""
    if isinstance(profile, OwnerProfile):
        return "owner_profile", "/owner/status"
    return "service_provider_profile", "/service-provider/status"


def _decide_document(db: Session, admin: User, profile, requirement_id: str, decision: DocumentStatus, note: str | None, expires_on):
    """Approve a document, or request its correction. A correction must say
    what to fix; an approval of a requirement that carries an expiry must
    record the expiry date. Every decision is audit-logged."""
    if decision not in (DocumentStatus.approved, DocumentStatus.rejected):
        raise HTTPException(status_code=400, detail="A document can only be approved or sent back for correction.")
    entry = next(((r, d) for r, d in checklist(db, profile) if r.id == requirement_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="Document not found.")
    req, doc = entry
    if doc.status == DocumentStatus.not_submitted:
        raise HTTPException(status_code=400, detail="This document hasn't been uploaded yet.")
    note = (note or "").strip() or None
    if decision == DocumentStatus.rejected and not note:
        raise HTTPException(status_code=400, detail="Say what needs to be corrected, so the account holder knows what to fix.")
    if decision == DocumentStatus.approved and req.requires_expiry and not expires_on:
        raise HTTPException(status_code=400, detail=f"{req.name} requires an expiry date when it is approved.")

    previous = doc.status.value
    doc.status = decision
    doc.admin_note = note if decision == DocumentStatus.rejected else None
    doc.reviewed_by = admin.id
    doc.reviewed_at = datetime.utcnow()
    doc.expires_on = expires_on if decision == DocumentStatus.approved else None
    if decision == DocumentStatus.rejected and not is_added_qualification(profile, req):
        # A correction sends the whole application back to the account holder
        # -- except for an optional qualification a verified account added
        # later, which is decided on its own (their access is untouched).
        profile.verification_status = VerificationStatus.changes_requested
    db.commit()

    target_type, link = _side(profile)
    log_action(
        db,
        actor_id=admin.id,
        action="document.approved" if decision == DocumentStatus.approved else "document.correction_requested",
        target_type=target_type,
        target_id=profile.user_id,
        previous_value=f"{req.name}: {previous}",
        new_value=f"{req.name}: {decision.value}" + (f" ({note})" if note else ""),
    )
    is_owner = isinstance(profile, OwnerProfile)
    if decision == DocumentStatus.approved:
        kind = NotificationType.owner_document_approved if is_owner else NotificationType.document_approved
    else:
        kind = NotificationType.owner_document_rejected if is_owner else NotificationType.document_rejected
    notify(db, profile.user, kind, link=link, requirement_name=req.name, note=note or "")
    db.refresh(doc)
    return doc, req


def _decide_application(db: Session, admin: User, profile, status: VerificationStatus, note: str | None) -> None:
    note = (note or "").strip() or None
    target_type, link = _side(profile)
    is_owner = isinstance(profile, OwnerProfile)
    if status == VerificationStatus.approved:
        assert_ready_to_approve(db, profile)
    elif status == VerificationStatus.changes_requested:
        flagged = any(d.status == DocumentStatus.rejected for _, d in checklist(db, profile))
        if not note and not flagged:
            raise HTTPException(
                status_code=400,
                detail="Request a correction on a specific document, or say what needs to change.",
            )
    elif status == VerificationStatus.rejected and not note:
        raise HTTPException(status_code=400, detail="Give the reason for rejecting this application.")

    previous = profile.verification_status.value
    profile.verification_status = status
    profile.verification_note = note
    db.commit()
    log_action(
        db,
        actor_id=admin.id,
        action="owner_verification_status.set" if is_owner else "verification_status.set",
        target_type=target_type,
        target_id=profile.user_id,
        previous_value=previous,
        new_value=status.value + (f" ({note})" if note else ""),
    )
    if status == VerificationStatus.approved:
        kind = NotificationType.owner_verification_activated if is_owner else NotificationType.verification_activated
        notify(db, profile.user, kind, link="/owner/dashboard" if is_owner else "/service-provider/dashboard")
    else:
        kind = NotificationType.verification_changes_requested if status == VerificationStatus.changes_requested else NotificationType.verification_rejected
        notify(db, profile.user, kind, link=link, note=note or "")
    db.refresh(profile)


@router.get("/review/queue")
def review_queue(db: Session = Depends(get_db)):
    profiles = (
        db.query(ServiceProviderProfile)
        .filter(
            ServiceProviderProfile.verification_status.in_(
                [VerificationStatus.pending_review, VerificationStatus.changes_requested]
            )
            # Stage 3.9: verified providers who added a qualification for review.
            | (
                (ServiceProviderProfile.verification_status == VerificationStatus.approved)
                & ServiceProviderProfile.user_id.in_(
                    db.query(ServiceProviderDocument.service_provider_id).filter(ServiceProviderDocument.status == DocumentStatus.pending)
                )
            )
        )
        .order_by(ServiceProviderProfile.created_at.asc())
        .all()
    )
    result = []
    for cp in profiles:
        docs = checklist(db, cp)
        db.commit()
        expiry = 60 * 60 * 24  # admin review links: fixed 24h window, not deadline-tied like drawings
        storage = get_storage()
        result.append(
            {
                "service_provider": ServiceProviderProfileOut(**_profile_fields(cp), email=None),
                "stakeholder": describe_stakeholder(cp, cp.user, db),
                "documents": [
                    {
                        **ServiceProviderDocumentOut(**document_out_fields(d, r)).model_dump(),
                        "url": storage.signed_url("service-provider-documents", d.file_path, expiry) if d.file_path else None,
                    }
                    for r, d in docs
                ],
            }
        )
    return result


@router.post("/review/documents", response_model=ServiceProviderDocumentOut)
def review_document(payload: ReviewDocumentDecision, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cp = _get_active_service_provider_profile(db, payload.service_provider_id)
    doc, req = _decide_document(db, admin, cp, payload.requirement_id, payload.decision, payload.note, payload.expires_on)
    return ServiceProviderDocumentOut(**document_out_fields(doc, req))


@router.patch("/documents/{document_id}/expiry", response_model=ServiceProviderDocumentOut)
def set_document_expiry(document_id: str, payload: DocumentExpiryUpdate, db: Session = Depends(get_db)):
    doc = db.get(ServiceProviderDocument, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.expires_on = payload.expires_on
    db.commit()
    db.refresh(doc)
    requirement = db.get(DocumentRequirement, doc.requirement_id)
    return ServiceProviderDocumentOut(
        id=doc.id,
        service_provider_id=doc.service_provider_id,
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


@router.post("/review/service-providers/{service_provider_id}/approve", response_model=ServiceProviderProfileOut)
def approve_service_provider(service_provider_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    cp = _get_active_service_provider_profile(db, service_provider_id)
    _decide_application(db, admin, cp, VerificationStatus.approved, None)
    return ServiceProviderProfileOut(**_profile_fields(cp), email=cp.user.email)


@router.post("/review/service-providers/{service_provider_id}/request-changes", response_model=ServiceProviderProfileOut)
def request_service_provider_changes(
    service_provider_id: str, payload: ApplicationDecision | None = None, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    cp = _get_active_service_provider_profile(db, service_provider_id)
    _decide_application(db, admin, cp, VerificationStatus.changes_requested, payload.note if payload else None)
    return ServiceProviderProfileOut(**_profile_fields(cp), email=cp.user.email)


@router.post("/review/service-providers/{service_provider_id}/reject", response_model=ServiceProviderProfileOut)
def reject_service_provider(
    service_provider_id: str, payload: ApplicationDecision, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    cp = _get_active_service_provider_profile(db, service_provider_id)
    _decide_application(db, admin, cp, VerificationStatus.rejected, payload.note)
    return ServiceProviderProfileOut(**_profile_fields(cp), email=cp.user.email)


# ---------- service provider management ----------

def _get_active_service_provider_profile(db: Session, service_provider_id: str) -> ServiceProviderProfile:
    """Same reasoning as _get_active_owner_profile below (defined once
    OwnerProfile existed and this mirror was written to match): the
    documented way to create an admin is to sign up as an owner OR
    service provider and flip the role column, which leaves a real
    service_provider_profiles row behind for an account that's no longer a
    service provider. Every mutation below goes through this instead of a bare
    db.get(ServiceProviderProfile, service_provider_id)."""
    cp = db.get(ServiceProviderProfile, service_provider_id)
    user = db.get(User, service_provider_id)
    if not cp or not user or user.role != UserRole.service_provider:
        raise HTTPException(status_code=404, detail="Service provider not found.")
    return cp


@router.get("/service-providers", response_model=list[ServiceProviderProfileOut])
def list_service_providers(db: Session = Depends(get_db)):
    rows = (
        db.query(ServiceProviderProfile, User)
        .join(User, ServiceProviderProfile.user_id == User.id)
        .filter(User.role == UserRole.service_provider)
        .all()
    )
    return [ServiceProviderProfileOut(**_profile_fields(cp), email=u.email) for cp, u in rows]


@router.get("/service-providers/{service_provider_id}")
def service_provider_detail(service_provider_id: str, db: Session = Depends(get_db)):
    cp = _get_active_service_provider_profile(db, service_provider_id)
    user = db.get(User, service_provider_id)
    docs = checklist(db, cp)
    db.commit()
    storage = get_storage()
    return {
        "service_provider": ServiceProviderProfileOut(**_profile_fields(cp), email=user.email if user else None),
        "stakeholder": describe_stakeholder(cp, user, db) if user else None,
        "documents": [
            {
                **ServiceProviderDocumentOut(**document_out_fields(d, r)).model_dump(),
                "url": storage.signed_url("service-provider-documents", d.file_path, _ADMIN_LINK_SECONDS) if d.file_path else None,
            }
            for r, d in docs
        ],
    }


@router.patch("/service-providers/{service_provider_id}", response_model=ServiceProviderProfileOut)
def update_service_provider(service_provider_id: str, payload: ServiceProviderProfileUpdate, db: Session = Depends(get_db)):
    cp = _get_active_service_provider_profile(db, service_provider_id)
    if not payload.company_name.strip():
        raise HTTPException(status_code=400, detail="Company name is required.")

    cp.company_name = payload.company_name.strip()
    cp.license_number = payload.license_number or None
    cp.primary_trade = payload.primary_trade or None
    cp.service_area = payload.service_area or None
    db.commit()
    db.refresh(cp)
    user = db.get(User, service_provider_id)
    return ServiceProviderProfileOut(**_profile_fields(cp), email=user.email if user else None)


class VerificationStatusPatch(BaseModel):
    status: VerificationStatus


@router.post("/service-providers/{service_provider_id}/verification-status", response_model=ServiceProviderProfileOut)
def set_verification_status(
    service_provider_id: str,
    payload: VerificationStatusPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cp = _get_active_service_provider_profile(db, service_provider_id)
    previous = cp.verification_status.value
    cp.verification_status = payload.status
    db.commit()
    db.refresh(cp)
    log_action(
        db,
        actor_id=admin.id,
        action="verification_status.set",
        target_type="service_provider_profile",
        target_id=service_provider_id,
        previous_value=previous,
        new_value=payload.status.value,
    )
    return cp


class SuspendPatch(BaseModel):
    suspended: bool


@router.post("/service-providers/{service_provider_id}/suspend", response_model=ServiceProviderProfileOut)
def set_suspended(
    service_provider_id: str,
    payload: SuspendPatch,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cp = _get_active_service_provider_profile(db, service_provider_id)
    previous = cp.is_suspended
    cp.is_suspended = payload.suspended
    db.commit()
    db.refresh(cp)
    log_action(
        db,
        actor_id=admin.id,
        action="service_provider.suspend" if payload.suspended else "service_provider.reactivate",
        target_type="service_provider_profile",
        target_id=service_provider_id,
        previous_value=str(previous),
        new_value=str(payload.suspended),
    )
    service_provider_user = db.get(User, service_provider_id)
    if service_provider_user:
        notify(
            db,
            service_provider_user,
            NotificationType.service_provider_suspended if payload.suspended else NotificationType.service_provider_reactivated,
            link="/service-provider/dashboard",
        )
    return cp


# ---------- payment override (spec P0: admin can activate a verified
# service provider's marketplace access without a real subscription, but only
# with a recorded reason — every grant/revoke is audited) ----------

class PaymentOverrideGrant(BaseModel):
    reason: str


@router.post("/service-providers/{service_provider_id}/payment-override", response_model=ServiceProviderProfileOut)
def grant_payment_override(
    service_provider_id: str,
    payload: PaymentOverrideGrant,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required to grant a payment override.")

    cp = _get_active_service_provider_profile(db, service_provider_id)

    previous = cp.payment_override_active
    db.add(PaymentOverride(service_provider_id=service_provider_id, granted_by=admin.id, reason=reason))
    cp.payment_override_active = True
    db.commit()
    db.refresh(cp)

    log_action(
        db,
        actor_id=admin.id,
        action="payment_override.grant",
        target_type="service_provider_profile",
        target_id=service_provider_id,
        previous_value=str(previous),
        new_value="True",
        reason=reason,
    )

    user = db.get(User, service_provider_id)
    if user:
        notify(db, user, NotificationType.payment_override_granted, link="/service-provider/dashboard")
    return ServiceProviderProfileOut(**_profile_fields(cp), email=user.email if user else None)


class PaymentOverrideRevoke(BaseModel):
    reason: str | None = None


@router.post("/service-providers/{service_provider_id}/payment-override/revoke", response_model=ServiceProviderProfileOut)
def revoke_payment_override(
    service_provider_id: str,
    payload: PaymentOverrideRevoke,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cp = _get_active_service_provider_profile(db, service_provider_id)

    previous = cp.payment_override_active
    active = (
        db.query(PaymentOverride)
        .filter(PaymentOverride.service_provider_id == service_provider_id, PaymentOverride.revoked_at.is_(None))
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
        target_type="service_provider_profile",
        target_id=service_provider_id,
        previous_value=str(previous),
        new_value="False",
        reason=payload.reason,
    )

    user = db.get(User, service_provider_id)
    if user:
        notify(db, user, NotificationType.payment_override_revoked, link="/service-provider/dashboard")
    return ServiceProviderProfileOut(**_profile_fields(cp), email=user.email if user else None)


@router.get("/service-providers/{service_provider_id}/payment-overrides")
def list_payment_overrides(service_provider_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(PaymentOverride)
        .filter(PaymentOverride.service_provider_id == service_provider_id)
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


@router.get("/service-providers/{service_provider_id}/audit-log")
def service_provider_audit_log(service_provider_id: str, db: Session = Depends(get_db)):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.target_type == "service_provider_profile", AuditLog.target_id == service_provider_id)
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

    # Built-in keys first, in the order they appear on the site; any extra
    # keys an admin stored outside the defaults follow alphabetically.
    ordered = list(DEFAULT_CMS.keys()) + sorted(keys - DEFAULT_CMS.keys())
    return [CmsEntry(key=k, en=resolve(k, Language.en), ar=resolve(k, Language.ar)) for k in ordered]


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


# Permanently removes the service provider's account, which cascades through
# service_provider_profiles → service_provider_documents/offers via FK ON DELETE
# CASCADE. Blocked if the service provider has any reviews on record — those are
# part of the platform's public reputation history and reviews.service_provider_id
# has no cascade by design, so a hard delete would otherwise violate that
# foreign key. Suspend instead to preserve history while cutting access.
@router.delete("/service-providers/{service_provider_id}", status_code=204)
def delete_service_provider(service_provider_id: str, db: Session = Depends(get_db)):
    _get_active_service_provider_profile(db, service_provider_id)  # 404s outright for a since-promoted admin account

    review_count = db.query(Review).filter(Review.service_provider_id == service_provider_id).count()
    if review_count > 0:
        raise HTTPException(
            status_code=400,
            detail="This service provider has completed projects with reviews on record. Suspend the account instead of deleting it, to keep that history intact.",
        )

    docs_with_files = (
        db.query(ServiceProviderDocument.file_path)
        .filter(ServiceProviderDocument.service_provider_id == service_provider_id, ServiceProviderDocument.file_path.isnot(None))
        .all()
    )
    paths = [p[0] for p in docs_with_files if p[0]]
    if paths:
        get_storage().delete("service-provider-documents", paths)

    user = db.get(User, service_provider_id)
    if not user:
        raise HTTPException(status_code=404, detail="Service provider not found.")
    db.delete(user)  # cascades to service_provider_profiles -> service_provider_documents/offers
    db.commit()
    return None


# ---------- owner management (mirrors the service provider management section
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
        **profile_state_fields(op),
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


def _owner_documents(db: Session, owner_id: str) -> list[dict]:
    docs = checklist(db, db.get(OwnerProfile, owner_id))
    db.commit()
    storage = get_storage()
    return [
        {
            **OwnerDocumentOut(**document_out_fields(d, r)).model_dump(),
            "url": storage.signed_url("owner-documents", d.file_path, _ADMIN_LINK_SECONDS) if d.file_path else None,
        }
        for r, d in docs
    ]


@router.get("/owners", response_model=list[OwnerProfileOut])
def list_owners(db: Session = Depends(get_db)):
    # Filtered to users whose CURRENT role is still owner: the documented
    # way to create an admin account is to sign up as an owner (or
    # service provider) and flip that row's role in the database (see README's
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
        "stakeholder": describe_stakeholder(op, user, db),
        "documents": _owner_documents(db, owner_id),
    }


@router.post("/review/owner-documents", response_model=OwnerDocumentOut)
def review_owner_document(
    payload: ReviewOwnerDocumentDecision, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    op = _get_active_owner_profile(db, payload.owner_id)
    doc, req = _decide_document(db, admin, op, payload.requirement_id, payload.decision, payload.note, payload.expires_on)
    return OwnerDocumentOut(**document_out_fields(doc, req))


@router.post("/review/owners/{owner_id}/approve", response_model=OwnerProfileOut)
def approve_owner(owner_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    op = _get_active_owner_profile(db, owner_id)
    _decide_application(db, admin, op, VerificationStatus.approved, None)
    return OwnerProfileOut(**_owner_fields(op, op.user))


@router.post("/review/owners/{owner_id}/request-changes", response_model=OwnerProfileOut)
def request_owner_changes(
    owner_id: str, payload: ApplicationDecision | None = None, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    op = _get_active_owner_profile(db, owner_id)
    _decide_application(db, admin, op, VerificationStatus.changes_requested, payload.note if payload else None)
    return OwnerProfileOut(**_owner_fields(op, op.user))


@router.post("/review/owners/{owner_id}/reject", response_model=OwnerProfileOut)
def reject_owner(owner_id: str, payload: ApplicationDecision, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    op = _get_active_owner_profile(db, owner_id)
    _decide_application(db, admin, op, VerificationStatus.rejected, payload.note)
    return OwnerProfileOut(**_owner_fields(op, op.user))


@router.post("/owners/{owner_id}/verification-status", response_model=OwnerProfileOut)
def set_owner_verification_status(
    owner_id: str, payload: VerificationStatusPatch, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """Manual override, mirroring the service provider one -- e.g. to reopen a
    rejected application."""
    op = _get_active_owner_profile(db, owner_id)
    previous = op.verification_status.value
    op.verification_status = payload.status
    db.commit()
    log_action(
        db,
        actor_id=admin.id,
        action="owner_verification_status.set",
        target_type="owner_profile",
        target_id=owner_id,
        previous_value=previous,
        new_value=payload.status.value,
    )
    return OwnerProfileOut(**_owner_fields(op, op.user))


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


# Permanently removes the owner's account. Unlike delete_service_provider
# (which only cascades to that service provider's own documents/offers —
# projects and other bidders' data are untouched), projects.owner_id has
# ON DELETE CASCADE: deleting an owner would silently wipe every project
# they ever posted, including drawings, clarifications, and every
# SERVICE_PROVIDER'S offers/reviews on those projects — data that belongs to
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
            detail="This owner has posted projects. Suspend the account instead of deleting it, to keep that project and offer history intact for the service providers involved.",
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
        db.query(Offer, Project, ServiceProviderProfile)
        .join(Project, Offer.project_id == Project.id)
        .outerjoin(ServiceProviderProfile, Offer.service_provider_id == ServiceProviderProfile.user_id)
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
            "service_provider_id": o.service_provider_id,
            "service_provider_company_name": cp.company_name if cp else None,
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
# any owner's projects and any service provider's offers on them, per the same
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
        "bid_deadline": utc_iso(p.bid_deadline),
        "status": p.status,
        "closure_reason": p.closure_reason,  # Stage 3.16: why it ended, if without an award
        "closed_at": p.closed_at,
        "tender_type": p.tender_type,
        "tender_type_locked": p.tender_type_locked,
        "is_suspended": p.is_suspended,
        "created_at": p.created_at,
    }


def _offer_admin_fields(o: Offer, p: Project | None, cp: ServiceProviderProfile | None) -> dict:
    return {
        "id": o.id,
        "project_id": o.project_id,
        "project_title": p.title if p else None,
        "project_status": p.status if p else None,
        "tender_type": p.tender_type if p else None,
        "service_provider_id": o.service_provider_id,
        "service_provider_company_name": cp.company_name if cp else None,
        "amount": str(o.amount) if o.amount is not None else None,
        "item_prices": o.item_prices,
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
        db.query(Offer, ServiceProviderProfile)
        .outerjoin(ServiceProviderProfile, Offer.service_provider_id == ServiceProviderProfile.user_id)
        .filter(Offer.project_id == project_id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    return {
        "project": _project_admin_fields(project, owner),
        "offers": [_offer_admin_fields(o, project, cp) for o, cp in offer_rows],
        # What an offer's price is measured against (Stage 3.4), so an admin
        # correction can follow it.
        "pricing_basis": project.pricing_basis,
        "items": [{"id": i.id, "position": i.position, "description": i.description, "quantity": str(i.quantity) if i.quantity is not None else None, "unit": i.unit} for i in project.items],
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
        # Same resolution as the owner's: a name on the platform's list links
        # that category; other text stays free text.
        category_value, trade = resolve_trade(db, None, payload.trade)
        if project.status != ProjectStatus.draft and rules_for(project).match_category and category_value != project.category_id:
            raise HTTPException(status_code=409, detail="Who can respond depends on this requirement's type of work, so it can't be changed after publishing.")
        changed.append("trade")
        project.category_id, project.trade = category_value, trade
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
        notify_team(
            db,
            owner,
            NotificationType.project_suspended if payload.suspended else NotificationType.project_reactivated,
            organization_id=project.organization_id,
            link=f"/owner/projects/{project_id}",
            project_title=project.title,
        )
    return _project_admin_fields(project, owner)


# Blocked outright once the project has any offers on it — deleting it
# would cascade through offers.project_id (ON DELETE CASCADE) and silently
# erase every service provider's bid history on this project, data that belongs
# to them, not just this owner. Suspend instead, same reasoning as
# delete_owner/delete_service_provider above.
@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    offer_count = db.query(Offer).filter(Offer.project_id == project_id).count()
    if offer_count > 0:
        raise HTTPException(
            status_code=400,
            detail="This project has offers on it. Suspend it instead of deleting it, to keep that bid history intact for the service providers involved.",
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
    # For a requirement priced per item: corrected rates (the total follows).
    item_prices: list[OfferItemPrice] | None = None


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

    # The same rules as the provider's own submission (routers/offers.py):
    # an edited bid must still come from an eligible provider (Stage 3.9) and
    # still meet the requirement's pricing basis and response rules (3.8).
    reasons = ineligibility_reasons(db, project, db.get(ServiceProviderProfile, offer.service_provider_id)) if project else []
    if reasons:
        raise HTTPException(
            status_code=409,
            detail="This provider isn't eligible for this requirement, so the bid can't be changed. " + " ".join(r.message for r in reasons),
        )
    per_item = project is not None and project.pricing_basis == PricingBasis.per_item
    if per_item and payload.amount is not None and payload.item_prices is None:
        raise HTTPException(status_code=400, detail="This requirement is priced per item: correct the item rates and the total follows.")
    if not per_item and payload.item_prices is not None:
        raise HTTPException(status_code=400, detail="This requirement is priced as one total: correct the amount.")
    merged = OfferCreate(
        amount=payload.amount if payload.amount is not None else offer.amount,
        item_prices=payload.item_prices if payload.item_prices is not None else (
            [OfferItemPrice(item_id=line["item_id"], rate=line["rate"]) for line in offer.item_prices] if offer.item_prices else None
        ),
        timeline_estimate=payload.timeline_estimate if payload.timeline_estimate is not None else offer.timeline_estimate,
        message=payload.message if payload.message is not None else offer.message,
        assumptions=offer.assumptions,
        accepted_declarations=offer.declarations_accepted or [],
    )
    amount, item_prices = priced_total(project, merged) if project else (merged.amount, None)
    if amount is None or amount <= 0:
        raise HTTPException(status_code=400, detail="Enter a valid bid amount.")
    if project:
        check_complete(db, project, offer.organization_id, offer.service_provider_id, merged)

    changed: list[str] = []
    if amount != offer.amount:
        changed.append("amount")
    if item_prices is not None and item_prices != offer.item_prices:
        changed.append("item_prices")
    if payload.timeline_estimate is not None and payload.timeline_estimate != offer.timeline_estimate:
        changed.append("timeline_estimate")
    if payload.message is not None and payload.message != offer.message:
        changed.append("message")

    if not changed:
        raise HTTPException(status_code=400, detail="No changes were provided.")

    previous_values = {field: getattr(offer, field) for field in changed}
    _snapshot_revision(db, offer)
    offer.amount = amount
    if item_prices is not None:
        offer.item_prices = item_prices
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
    cp = db.get(ServiceProviderProfile, offer.service_provider_id)
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
    service_provider_user = db.get(User, offer.service_provider_id)
    if service_provider_user and project:
        notify_team(
            db,
            service_provider_user,
            NotificationType.offer_suspended if payload.suspended else NotificationType.offer_reactivated,
            organization_id=offer.organization_id,
            link=f"/service-provider/projects/{project.id}/offer",
            project_title=project.title,
        )
    cp = db.get(ServiceProviderProfile, offer.service_provider_id)
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
            "service_provider_id": offer.service_provider_id,
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


def _profile_fields(cp: ServiceProviderProfile) -> dict:
    return dict(
        user_id=cp.user_id,
        company_name=cp.company_name,
        license_number=cp.license_number,
        primary_trade=cp.primary_trade,
        service_area=cp.service_area,
        service_categories=cp.service_categories or [],
        service_governorates=cp.service_governorates or [],
        verification_status=cp.verification_status,
        is_suspended=cp.is_suspended,
        avg_rating=cp.avg_rating,
        review_count=cp.review_count,
        subscription_status=cp.subscription_status,
        subscription_current_period_end=cp.subscription_current_period_end,
        payment_override_active=cp.payment_override_active,
        marketplace_status=cp.marketplace_status,
        created_at=cp.created_at,
        **profile_state_fields(cp),
    )
