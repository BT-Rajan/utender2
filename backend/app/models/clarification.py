from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import gen_uuid


# Tender-specific Q&A (spec §2.7, D-008). One row per question; answer +
# answered_at stay null until the owner responds. shared_with_all controls
# whether other eligible bidders see this Q&A pair once answered — a
# private clarification stays visible only to the asking service provider and
# the owner.
class Clarification(Base):
    __tablename__ = "clarifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    service_provider_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("service_provider_profiles.user_id", ondelete="CASCADE"), nullable=False
    )
    # The organization this was done for (services.team); NULL = an individual's.
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_with_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stage 4.7: who on the owner's side answered, and -- when the answer
    # changed the requirement itself -- the amendment that did it, so a
    # material clarification is never just text beside an unchanged record.
    answered_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    amendment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("project_amendments.id", ondelete="SET NULL"), nullable=True)


# A file attached to a question (by the asker's side) or to its answer (by the
# owner's side) -- a marked-up drawing, a photo of the site. Seen by exactly
# whoever can see that question or answer; served through the same signed,
# short-lived, named links as the requirement's own documents.
class ClarificationAttachment(Base):
    __tablename__ = "clarification_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    clarification_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clarifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part: Mapped[str] = mapped_column(String(10), nullable=False)  # "question" | "answer"
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
