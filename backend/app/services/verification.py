"""Step 4: verification policy -> checklist -> review -> eligibility.

Admins own the policy (Admin -> Document requirements): each requirement
names the role it applies to, optionally the stakeholder type (individual /
organization; NULL = both), whether it is required, whether its approval must
carry an expiry date, and whether it is active. Nothing here, or in the owner
and service-provider flows, names a specific document.

A profile's checklist is always computed from the *current* policy for that
profile's role and stakeholder type, so a newly initiated verification gets
whatever the admin has configured now. Missing document rows are created on
demand; existing approvals are never touched, so a policy change does not
silently invalidate anyone (see the effective_from note on
DocumentRequirement for how stricter terms are flagged for re-review).
"""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session, object_session

from app.models.document import DocumentRequirement, OwnerDocument, ServiceProviderDocument
from app.models.enums import DocumentStatus, StakeholderType, UserRole, VerificationStatus
from app.models.owner import OwnerProfile
from app.models.service_provider import ServiceProviderProfile

# Verification may be filled in / corrected only in these states.
EDITABLE_STATUSES = (VerificationStatus.incomplete, VerificationStatus.changes_requested)


def applicable_requirements(db: Session, role: UserRole, stakeholder_type: StakeholderType | None) -> list[DocumentRequirement]:
    """The single policy selector. A country (or any other) scope would be
    one more filter here."""
    query = db.query(DocumentRequirement).filter(
        DocumentRequirement.is_active.is_(True), DocumentRequirement.applies_to == role
    )
    if stakeholder_type is None:
        # Not established yet: only requirements that apply to everyone.
        query = query.filter(DocumentRequirement.applies_to_stakeholder.is_(None))
    else:
        query = query.filter(
            (DocumentRequirement.applies_to_stakeholder.is_(None))
            | (DocumentRequirement.applies_to_stakeholder == stakeholder_type)
        )
    return query.order_by(DocumentRequirement.created_at.asc()).all()


def _doc_model(profile):
    if isinstance(profile, OwnerProfile):
        return OwnerDocument, OwnerDocument.owner_id, UserRole.owner
    return ServiceProviderDocument, ServiceProviderDocument.service_provider_id, UserRole.service_provider


def checklist(db: Session, profile) -> list[tuple[DocumentRequirement, OwnerDocument | ServiceProviderDocument]]:
    """(requirement, document row) for every requirement that currently
    applies to this profile, creating not-yet-submitted rows as needed.
    Rows for requirements that no longer apply (retired, or for the other
    stakeholder type) are kept for history but are not part of it."""
    model, owner_col, role = _doc_model(profile)
    requirements = applicable_requirements(db, role, profile.stakeholder_type)
    rows = {d.requirement_id: d for d in db.query(model).filter(owner_col == profile.user_id).all()}
    created = False
    for req in requirements:
        if req.id not in rows:
            kwargs = {"owner_id" if model is OwnerDocument else "service_provider_id": profile.user_id}
            rows[req.id] = model(requirement_id=req.id, **kwargs)
            db.add(rows[req.id])
            created = True
    if created:
        db.flush()
    return [(req, rows[req.id]) for req in requirements]


def assert_editable(profile) -> None:
    if profile.is_suspended or profile.verification_status not in EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Documents can only be uploaded while your verification is being completed or corrected.",
        )


def assert_ready_to_submit(db: Session, profile) -> None:
    missing = [req.name for req, doc in checklist(db, profile) if req.is_required and doc.status in (DocumentStatus.not_submitted, DocumentStatus.rejected)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="All required documents must be uploaded (and any correction made) before submitting for review: " + ", ".join(missing) + ".",
        )


def mark_submitted(profile) -> None:
    profile.verification_status = VerificationStatus.pending_review
    profile.verification_submitted_at = datetime.utcnow()
    profile.verification_note = None


def assert_ready_to_approve(db: Session, profile) -> None:
    pending = [req.name for req, doc in checklist(db, profile) if req.is_required and doc.status != DocumentStatus.approved]
    if pending:
        raise HTTPException(
            status_code=400,
            detail="All required documents must be approved before approving this account. Still open: " + ", ".join(pending) + ".",
        )


def verification_state(profile) -> str:
    """The user-facing state, derived from the stored status (which stays
    the source of truth) plus the documents:

      not_started         nothing uploaded yet
      incomplete          some documents uploaded, not submitted
      submitted           submitted, no review decision since
      under_review        submitted, an admin has started deciding documents
      correction_required changes requested (see document notes / verification_note)
      approved
      rejected            final refusal (see verification_note)
    """
    status = profile.verification_status
    if status == VerificationStatus.approved:
        return "approved"
    if status == VerificationStatus.rejected:
        return "rejected"
    if status == VerificationStatus.changes_requested:
        return "correction_required"
    db = object_session(profile)
    model, owner_col, _ = _doc_model(profile)
    docs = db.query(model).filter(owner_col == profile.user_id).all() if db else []
    if status == VerificationStatus.pending_review:
        since = profile.verification_submitted_at
        # Strictly after: MySQL keeps whole seconds, so a decision from the
        # previous round can share the resubmission's timestamp.
        started = any(d.reviewed_at and (since is None or d.reviewed_at > since) for d in docs)
        return "under_review" if started else "submitted"
    return "incomplete" if any(d.status != DocumentStatus.not_submitted for d in docs) else "not_started"


def profile_state_fields(profile) -> dict:
    return dict(
        verification_state=verification_state(profile),
        verification_note=profile.verification_note,
        verification_submitted_at=profile.verification_submitted_at,
    )


def document_out_fields(doc, req: DocumentRequirement | None) -> dict:
    """Shared field set for OwnerDocumentOut / ServiceProviderDocumentOut."""
    owner_key = "owner_id" if isinstance(doc, OwnerDocument) else "service_provider_id"
    return {
        "id": doc.id,
        owner_key: getattr(doc, owner_key),
        "requirement_id": doc.requirement_id,
        "status": doc.status,
        "admin_note": doc.admin_note,
        "reviewed_at": doc.reviewed_at,
        "submitted_at": doc.submitted_at,
        "expires_on": doc.expires_on,
        "requirement_name": req.name if req else None,
        "requirement_description": req.description if req else None,
        "requirement_is_required": req.is_required if req else None,
        "requirement_effective_from": req.effective_from if req else None,
        "requirement_requires_expiry": req.requires_expiry if req else None,
    }
