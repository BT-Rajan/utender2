from datetime import date, datetime

from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy import event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.common import gen_uuid
from app.models.enums import PricingBasis, ProjectStatus, TenderType


def _now_s() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The organization this was done for (services.team); NULL = an individual's.
    organization_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
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
    # Stage 3.10: the rules of participation, as distinct from what is being
    # requested (title/scope/items above). The offer deadline (bid_deadline),
    # the offer visibility (tender_type) and the declarations
    # (response_requirements) already exist; these complete them.
    # Questions: whether providers may ask, and until when (NULL = until
    # offers close). Enforced by services.tender_rules.
    questions_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    questions_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Conditions the price is given under (payment stages, retention,
    # warranty, offer validity...) and anything a provider must know or do
    # before responding (site visit arrangements, access...). Free text, as
    # the owner writes them; nothing is assumed.
    commercial_terms: Mapped[str | None] = mapped_column(Text, nullable=True)  # "other conditions"
    # Stage 3.12: the owner says providers can't price this without its
    # documents (drawings, BOQ, photos). The quality gate then requires at
    # least one -- an explicit statement, not a guess from the wording.
    documents_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # The common commercial terms as structured fields (schemas.project.
    # CommercialConditions): offer validity, payment stages, retention,
    # warranty. Each optional; NULL = none stated.
    commercial_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    bidder_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Admin moderation flag — independent of the owner-driven lifecycle
    # `status` above. Hides the project from the service provider feed and blocks
    # new bids while set, but leaves `status` untouched so un-suspending
    # restores exactly the state the project was in before.
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Sequential per project; bumped by the amendment service whenever a
    # published tender's material fields change (spec §2.8/§2.12).
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Stage 3.14: when it was published -- set once, by the server, in the
    # same transaction that makes it open. NULL = never published.
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stage 3.15: post-publication control.
    # The owner paused participation (still open, but no offers, changes,
    # withdrawals or questions until resumed). NULL = not paused. Distinct
    # from is_suspended, which is admin moderation that hides the project.
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When offers stopped being accepted (closed early, or at the deadline).
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Stage 3.16: why a requirement ended without a U-Tender award, within
    # its terminal status (no new states): canceled -> not_needed |
    # postponed | other; no_award -> no_suitable_offer | closed_externally.
    # Expired needs no reason (the deadline passed with no live offer).
    closure_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # The owner's private note on why it ended: shown to the owner side and admins, never to providers.
    closure_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stage 4.2 follow-up, derived on every save (sync_derived below), never
    # set directly: normalized text for the provider feed's search, and the
    # eligibility rules as plain columns so the feed can apply them in the
    # database query (services.eligibility.feed_condition).
    search_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    search_trade: Mapped[str | None] = mapped_column(String(150), nullable=True)
    search_place: Mapped[str | None] = mapped_column(String(300), nullable=True)
    search_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    elig_org_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    elig_match_category: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    elig_match_governorate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    elig_quals: Mapped[str | None] = mapped_column(String(2000), nullable=True)  # ",id,id," or NULL
    # The ended requirement this draft was started again from (Stage 3.16).
    restarted_from_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    # How many material amendments (changes to what providers price) have been
    # made since publication; an offer made against an earlier one is flagged.
    material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deadline_reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # Stage 3.11 (drafts): when the requirement was last saved (shown as
    # "last saved"), and its version: +1 on every save, checked under the
    # row lock against the version the saving page last saw (If-Match), so a
    # stale page can never overwrite newer work -- however close together
    # the two saves are.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=_now_s, onupdate=_now_s)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # A draft the owner deliberately discarded. It stays a draft (so it is as
    # private as ever) but is no longer active: not listed, not editable,
    # not publishable. Soft, so the audit trail keeps pointing at a record.
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Sent with the "start a requirement" request so a repeated submission
    # (double click, retry, resend after a dropped response) returns the
    # draft already created instead of making a second one.
    creation_token: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (UniqueConstraint("owner_id", "creation_token", name="uq_project_creation_token"),)

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
    # Stage 3.17: the requirement's material version this file became current
    # in (0 = as published). With the revision chain, it says which documents
    # an offer made against a given version was priced on.
    material_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Stage 4.4 follow-up: the file's size, so a provider knows what they're
    # downloading. NULL only for a file whose size couldn't be read back.
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project = relationship("Project", back_populates="drawings")


def sync_derived(project: "Project") -> None:
    """Recompute the derived search and eligibility columns from the record."""
    from app.services.search_text import GOVERNORATE_NAMES, normalize

    project.search_title = normalize(project.title)[:300]
    project.search_trade = normalize(project.trade)[:150] or None
    project.search_place = normalize(" ".join(x for x in (project.area, GOVERNORATE_NAMES.get(project.governorate or "")) if x))[:300] or None
    project.search_scope = normalize(project.description) or None
    rules = project.provider_eligibility or {}
    project.elig_org_only = rules.get("provider_type") == "organization"
    project.elig_match_category = bool(rules.get("match_category"))
    project.elig_match_governorate = bool(rules.get("match_governorate"))
    quals = sorted(set(rules.get("qualifications") or []))
    project.elig_quals = ("," + ",".join(quals) + ",") if quals else None


@event.listens_for(Project, "before_insert")
@event.listens_for(Project, "before_update")
def _sync_derived(mapper, connection, project) -> None:
    sync_derived(project)
