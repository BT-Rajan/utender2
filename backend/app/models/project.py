from datetime import date, datetime

from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import PricingBasis, ProjectStatus, TenderType


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Exact address or site description. Shown only where a provider can open
    # the full requirement (verified with active access); listings show the
    # governorate and area instead.
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    # Stage 3.5: where the work is, at the level providers use to judge
    # relevance and travel. governorate is one of KUWAIT_GOVERNORATES.
    governorate: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The type of work, as shown. When filed under one of the platform's
    # service categories, category_id links it and trade holds that
    # category's name (kept in step by services.categories).
    trade: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("service_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # The response deadline: the one authoritative closing time for offers.
    bid_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Stage 3.7: when the owner expects the work itself to happen (calendar
    # dates, no time of day). Optional; a completion date or a duration.
    expected_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=True), nullable=False, default=ProjectStatus.open, index=True
    )
    # Owner's choice at creation (spec §19-21, D-001): Sealed hides bidder
    # identity/amount/message/attachments from the owner until close;
    # Owner-Visible lets the owner see bids as they arrive. Locked once
    # tender_type_locked flips true (first valid bid submitted) — a
    # material tender condition can't be changed mid-bidding.
    tender_type: Mapped[TenderType] = mapped_column(
        Enum(TenderType, native_enum=True), nullable=False, default=TenderType.owner_visible
    )
    tender_type_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pricing_basis: Mapped[PricingBasis] = mapped_column(
        Enum(PricingBasis, native_enum=True), nullable=False, default=PricingBasis.lump_sum
    )
    # Stage 3.8: what a provider must submit beyond the price (see
    # schemas.project.ResponseRequirements). NULL = the defaults: price only,
    # everything else optional.
    response_requirements: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Stage 3.9: who may respond (see schemas.project.ProviderEligibilityIn).
    # NULL = every verified provider with active access.
    provider_eligibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Admin moderation flag — independent of the owner-driven lifecycle
    # `status` above. Hides the project from the service provider feed and blocks
    # new bids while set, but leaves `status` untouched so un-suspending
    # restores exactly the state the project was in before.
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Sequential per project; bumped by the amendment service whenever a
    # published tender's material fields change (spec §2.8/§2.12).
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deadline_reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    drawings = relationship("ProjectDrawing", back_populates="project", cascade="all, delete-orphan")
    items = relationship(
        "ProjectItem", back_populates="project", cascade="all, delete-orphan", order_by="ProjectItem.position"
    )


# Stage 3.4: the measurable basis for pricing -- the work components a
# provider prices against, each with an optional quantity and unit and the
# specifications that affect its cost. Optional: a requirement that isn't
# naturally itemized simply has none.
class ProjectItem(Base):
    __tablename__ = "project_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Specifications, dimensions and any item-specific notes.
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)

    project = relationship("Project", back_populates="items")


class ProjectDrawing(Base):
    __tablename__ = "project_drawings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    # Versioning (spec §2.8, §25, §67): a revised drawing is a NEW row, not
    # an overwrite of the old one. is_current marks which row is the one
    # service providers should look at; superseded rows stay in the database and
    # in storage for audit purposes.
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    amendment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_amendments.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Stage 3.6: what the file is (one of DOCUMENT_CATEGORIES) and whether
    # providers need it to price the work (True) or it's supplementary.
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="drawing")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    project = relationship("Project", back_populates="drawings")
