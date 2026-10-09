import enum


class UserRole(str, enum.Enum):
    owner = "owner"
    service_provider = "service_provider"
    admin = "admin"


# Who a registered account represents in the marketplace (Step 3). Unset
# until the person says so after signup: account created != stakeholder
# established.
class StakeholderType(str, enum.Enum):
    individual = "individual"
    organization = "organization"


# A person's authority within an organization. admin = an authorized
# representative who may act for, and manage, the organization's account;
# member = belongs to it without that authority.
class MembershipRole(str, enum.Enum):
    admin = "admin"
    member = "member"


class Language(str, enum.Enum):
    en = "en"
    ar = "ar"


# Tender lifecycle. "open"/"closed"/"awarded"/"canceled" are the original
# values (kept, including the American spelling, so existing rows never
# need a data migration) — draft/under_evaluation/no_award/expired are
# additive per the master specification's tender lifecycle (spec §2.12).
class ProjectStatus(str, enum.Enum):
    draft = "draft"
    open = "open"
    closed = "closed"
    under_evaluation = "under_evaluation"
    awarded = "awarded"
    no_award = "no_award"
    canceled = "canceled"
    expired = "expired"


# Owner's choice at tender creation (spec §19-21, D-001). Locked once the
# first valid bid is submitted — see Project.tender_type_locked.
class TenderType(str, enum.Enum):
    sealed = "sealed"
    owner_visible = "owner_visible"


# Stage 3.4: what a service provider is asked to price. lump_sum = one total
# for the complete requirement (the only basis offers capture today);
# per_item = a price for each listed requirement item (offers gain per-item
# prices in the response step).
class PricingBasis(str, enum.Enum):
    lump_sum = "lump_sum"
    per_item = "per_item"


class OfferStatus(str, enum.Enum):
    # Stage 5.2: the provider's offer while it is being prepared -- started by
    # Participate, private to the provider's side, never seen by the owner,
    # competitors or counts (see models.offer.tendered), and only ever made
    # an offer by submitting it while bidding is open.
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    withdrawn = "withdrawn"


class VerificationStatus(str, enum.Enum):
    incomplete = "incomplete"
    pending_review = "pending_review"
    changes_requested = "changes_requested"
    approved = "approved"
    # Final decision: the application was refused (with a recorded reason).
    # Unlike changes_requested the person can't resubmit; an admin can
    # reopen it through the verification-status override.
    rejected = "rejected"


class DocumentStatus(str, enum.Enum):
    not_submitted = "not_submitted"
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


# Payment/subscription state (spec §2.11: "Not Started, Pending, Active,
# Past Due, Failed, Cancelled, Expired, Waived/Overridden"). trialing is
# kept for Stripe trial periods even though the spec doesn't name it
# separately; waived is set/cleared alongside a PaymentOverride row, never
# set directly by the Stripe webhook.
class SubscriptionStatus(str, enum.Enum):
    not_started = "not_started"
    pending = "pending"
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    failed = "failed"
    canceled = "canceled"
    expired = "expired"
    waived = "waived"


class AuthTokenType(str, enum.Enum):
    email_verify = "email_verify"
    password_reset = "password_reset"


class NotificationType(str, enum.Enum):
    document_rejected = "document_rejected"
    document_approved = "document_approved"
    verification_activated = "verification_activated"
    payment_activated = "payment_activated"
    payment_failed = "payment_failed"
    payment_override_granted = "payment_override_granted"
    payment_override_revoked = "payment_override_revoked"
    service_provider_suspended = "service_provider_suspended"
    service_provider_reactivated = "service_provider_reactivated"
    owner_verification_activated = "owner_verification_activated"
    owner_document_rejected = "owner_document_rejected"
    owner_document_approved = "owner_document_approved"
    owner_suspended = "owner_suspended"
    owner_reactivated = "owner_reactivated"
    document_expiring = "document_expiring"
    tender_amendment = "tender_amendment"
    drawing_revised = "drawing_revised"
    clarification_asked = "clarification_asked"
    clarification_answered = "clarification_answered"
    bid_submitted = "bid_submitted"
    bid_revised = "bid_revised"
    bid_withdrawn = "bid_withdrawn"
    deadline_approaching = "deadline_approaching"
    tender_closed = "tender_closed"
    evaluation_ready = "evaluation_ready"
    award_won = "award_won"
    award_lost = "award_lost"
    tender_cancelled = "tender_cancelled"
    tender_no_award = "tender_no_award"
    project_suspended = "project_suspended"
    project_reactivated = "project_reactivated"
    offer_suspended = "offer_suspended"
    offer_reactivated = "offer_reactivated"
    verification_changes_requested = "verification_changes_requested"
    verification_rejected = "verification_rejected"
    new_requirement = "new_requirement"
    tender_paused = "tender_paused"
    tender_resumed = "tender_resumed"
    requirement_ended = "requirement_ended"
    clarification_shared = "clarification_shared"
    offer_clarification_requested = "offer_clarification_requested"
    offer_clarification_answered = "offer_clarification_answered"
    work_started = "work_started"  # Stage 7.5: to the other party of the agreement
    execution_updated = "execution_updated"  # Stage 7.6: put on hold / resumed, to the other party
    milestone_updated = "milestone_updated"  # Stage 7.7: delivered (to the owner side), accepted / returned (to the winner)
    variation_updated = "variation_updated"  # Stage 7.8: proposed / agreed / rejected / withdrawn, to the other party
    review_received = "review_received"  # Stage 8.3/8.4: the other party reviewed the completed work
    review_response = "review_response"  # Stage 8.9: the reviewed party responded to the review
    # Batch A: the agreement's own steps, told to the other party.
    agreement_terms_confirmed = "agreement_terms_confirmed"
    agreement_in_force = "agreement_in_force"
    agreement_terminated = "agreement_terminated"
