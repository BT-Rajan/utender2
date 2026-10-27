"""A verified provider asking the U-Tender team to activate its marketplace
access, for when online subscription isn't available (or can't be used).
Recorded in the audit log; the admin overview lists the requests still open
(the provider still has no access) until an admin grants access."""
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.service_provider import ServiceProviderProfile

ACTION = "marketplace_access.requested"


def latest_request_at(db: Session, provider_id: str) -> datetime | None:
    return db.query(func.max(AuditLog.created_at)).filter(AuditLog.action == ACTION, AuditLog.target_id == provider_id).scalar()


def open_request_at(db: Session, cp: ServiceProviderProfile) -> datetime | None:
    """When this provider asked, while it is still waiting (no access yet)."""
    if cp.is_verified_active or cp.is_suspended:
        return None
    return latest_request_at(db, cp.user_id)


def open_requests(db: Session) -> list[tuple[str, str | None, datetime]]:
    """(provider id, name, asked at) for every request still waiting, oldest first."""
    latest = (
        db.query(AuditLog.target_id, func.max(AuditLog.created_at))
        .filter(AuditLog.action == ACTION)
        .group_by(AuditLog.target_id)
        .all()
    )
    out = []
    for provider_id, at in latest:
        cp = db.get(ServiceProviderProfile, provider_id)
        if cp is not None and open_request_at(db, cp) is not None:
            out.append((provider_id, cp.company_name, at))
    return sorted(out, key=lambda r: r[2])
