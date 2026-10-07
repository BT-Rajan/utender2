export type ProjectStatus =
  | "draft"
  | "open"
  | "closed"
  | "under_evaluation"
  | "awarded"
  | "no_award"
  | "canceled"
  | "expired";
export type TenderType = "sealed" | "owner_visible";
export type OfferStatus = "submitted" | "approved" | "rejected" | "withdrawn";
export type VerificationStatus = "incomplete" | "pending_review" | "changes_requested" | "approved" | "rejected";
export type DocumentStatus = "not_submitted" | "pending" | "approved" | "rejected";
export type SubscriptionStatus = "trialing" | "active" | "past_due" | "canceled";

export interface Project {
  id: string;
  owner_id: string;
  title: string;
  // Exact address: null in the service provider feed (listings show
  // governorate/area); present on the full requirement.
  address: string | null;
  governorate: string | null;
  area: string | null;
  description: string | null;
  // Stage 3.7: expected work timing (calendar dates, "YYYY-MM-DD"), separate
  // from bid_deadline -- the response deadline, sent as UTC ("...Z").
  expected_start_date: string | null;
  expected_completion_date: string | null;
  expected_duration_days: number | null;
  trade: string | null;
  bid_deadline: string;
  status: ProjectStatus;
  tender_type: TenderType;
  tender_type_locked: boolean;
  is_suspended: boolean;
  created_at: string;
  updated_at?: string | null;
  discarded_at?: string | null;
  version?: number;
  published_at?: string | null;
  paused_at?: string | null;
  pause_reason?: string | null;
  closed_at?: string | null;
  // Stage 3.16: why it ended without a U-Tender award (canceled / no_award only).
  closure_reason?: ClosureReason | null;
  closure_note?: string | null; // the owner side only
  material_revision?: number;
  documents_required?: boolean;
  offer_count: number;
  my_offer_status: OfferStatus | null;
  // Stage 3.9, provider feed only.
  eligible?: boolean | null;
  ineligible_reasons?: EligibilityReason[];
  category_id?: string | null;
}

export interface Drawing {
  id: string;
  file_name: string;
  uploaded_at: string;
  revision: number;
  is_current: boolean;
  // Stage 3.6: what the file is, and whether providers need it to price.
  category: DocumentCategory;
  is_required: boolean;
  url: string | null;
}

export type DocumentCategory = "drawing" | "boq" | "specification" | "photo" | "site" | "other";

export interface ProjectDetail extends Project {
  pricing_basis: PricingBasis;
  items: RequirementItem[];
  drawings: Drawing[];
  currency: string;
  response_requirements: ResponseRequirements;
  provider_eligibility: ProviderEligibility;
  tender_rules: TenderRules;
}

export interface CommercialConditions {
  offer_validity_days: number | null;
  payment_stages: { milestone: string; percent: string }[];
  retention_percent: string | null;
  retention_months: number | null;
  warranty_months: number | null;
}

// Stage 3.10: how the opportunity is run (separate from what is requested).
export interface TenderRules {
  questions_allowed: boolean;
  questions_deadline: string | null;
  questions_close_at: string | null;
  questions_open: boolean;
  commercial_conditions: CommercialConditions;
  commercial_terms: string | null;
  bidder_instructions: string | null;
}

export interface EligibilityQualification {
  id: string;
  name: string;
  description: string | null;
}

export interface ProviderEligibility {
  provider_type: "any" | "organization";
  qualifications: EligibilityQualification[];
  match_category: boolean;
  match_governorate: boolean;
  category: string | null;
  governorate: string | null;
}

// A reason code the interface translates, with the details to fill in.
export interface EligibilityReason {
  code: "organization_only" | "qualification_missing" | "qualification_expired" | "category_not_offered" | "governorate_not_served";
  name: string | null;
  date: string | null;
  governorate: string | null;
  message: string;
}

export interface EligibilityCheck {
  eligible: boolean;
  reasons: EligibilityReason[];
  rules: ProviderEligibility;
}

export interface ServiceCategory {
  id: string;
  name: string;
  is_active: boolean;
}

export interface ResponseRequirements {
  completion_period: "required" | "optional";
  approach: "required" | "optional";
  documents: { name: string; required: boolean }[];
  declarations: string[];
}

export interface OfferItemPrice {
  item_id: string;
  rate: string;
  line_total: string;
}

export interface OfferDocument {
  id: string;
  label: string;
  file_name: string;
  uploaded_at: string;
  url: string;
}

export interface Offer {
  id: string;
  project_id: string;
  service_provider_id: string | null;
  amount: string | null;
  timeline_estimate: string | null;
  message: string | null;
  status: OfferStatus;
  is_suspended: boolean;
  revision: number;
  based_on_material_revision?: number;
  created_at: string;
  updated_at: string;
  service_provider_company_name?: string | null;
  service_provider_avg_rating?: string | null;
  service_provider_review_count?: number | null;
  sealed: boolean;
  item_prices: OfferItemPrice[] | null;
  assumptions: string | null;
  declarations_accepted: string[] | null;
  documents: OfferDocument[];
}

export interface OfferRevision {
  id: string;
  offer_id: string;
  revision_number: number;
  amount: string;
  timeline_estimate: string | null;
  message: string | null;
  item_prices: OfferItemPrice[] | null;
  assumptions: string | null;
  status: OfferStatus;
  recorded_at: string;
}

export interface ServiceProviderProfile {
  user_id: string;
  company_name: string;
  license_number: string | null;
  primary_trade: string | null;
  service_area: string | null;
  service_categories: string[];
  service_governorates: string[];
  verification_status: VerificationStatus;
  is_suspended: boolean;
  avg_rating: string;
  review_count: number;
  subscription_status: SubscriptionStatus | null;
  subscription_current_period_end: string | null;
  payment_override_active: boolean;
  marketplace_status:
    | "documents_incomplete"
    | "submitted_for_review"
    | "changes_requested"
    | "rejected"
    | "payment_required"
    | "payment_restricted"
    | "verified_active"
    | "suspended";
  created_at: string;
  email?: string | null;
  verification_state: VerificationState;
  verification_note: string | null;
  verification_submitted_at: string | null;
}

export interface DocumentRequirement {
  id: string;
  name: string;
  description: string | null;
  is_required: boolean;
  is_active: boolean;
  applies_to: "owner" | "service_provider";
  applies_to_stakeholder: "individual" | "organization" | null; // null = both
  requires_expiry: boolean;
  effective_from: string;
  created_at: string;
}

export interface ServiceProviderDocument {
  id: string;
  service_provider_id: string;
  requirement_id: string;
  status: DocumentStatus;
  admin_note: string | null;
  reviewed_at: string | null;
  submitted_at: string | null;
  expires_on: string | null;
  requirement_name: string | null;
  requirement_description: string | null;
  requirement_is_required: boolean | null;
  requirement_effective_from: string | null;
  requirement_requires_expiry?: boolean | null;
  url?: string | null; // admin views only: a signed, time-limited link
}

export interface OwnerProfile {
  user_id: string;
  verification_status: VerificationStatus;
  is_suspended: boolean;
  marketplace_status: "documents_incomplete" | "submitted_for_review" | "changes_requested" | "rejected" | "verified_active" | "suspended";
  created_at: string;
  email?: string | null;
  full_name?: string | null;
  project_count: number;
  verification_state: VerificationState;
  verification_note: string | null;
  verification_submitted_at: string | null;
}

// Step 4 lifecycle, derived server-side (verification_status stays the stored truth).
export type VerificationState =
  | "not_started"
  | "incomplete"
  | "submitted"
  | "under_review"
  | "correction_required"
  | "approved"
  | "rejected";

export interface OwnerDocument {
  id: string;
  owner_id: string;
  requirement_id: string;
  status: DocumentStatus;
  admin_note: string | null;
  reviewed_at: string | null;
  submitted_at: string | null;
  expires_on: string | null;
  requirement_name: string | null;
  requirement_description: string | null;
  requirement_is_required: boolean | null;
  requirement_effective_from: string | null;
  requirement_requires_expiry?: boolean | null;
  url?: string | null; // admin views only: a signed, time-limited link
}

export type ClosureReason = "not_needed" | "postponed" | "other" | "no_suitable_offer" | "closed_externally";

export interface AdminOffer {
  id: string;
  project_id: string;
  project_title: string;
  project_status: ProjectStatus;
  tender_type: TenderType;
  service_provider_id: string | null;
  service_provider_company_name: string | null;
  amount: string | null;
  item_prices?: OfferItemPrice[] | null;
  timeline_estimate: string | null;
  message?: string | null;
  status: OfferStatus;
  is_suspended: boolean;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface AdminProject {
  id: string;
  owner_id: string;
  owner_name: string | null;
  owner_email: string | null;
  title: string;
  address: string;
  description: string | null;
  trade: string | null;
  bid_deadline: string;
  status: ProjectStatus;
  tender_type: TenderType;
  tender_type_locked: boolean;
  is_suspended: boolean;
  created_at: string;
  offer_count: number;
}

export interface AdminProjectDetail {
  project: AdminProject;
  offers: AdminOffer[];
  pricing_basis?: PricingBasis;
  items?: { id: string; position: number; description: string; quantity: string | null; unit: string | null }[];
}

export interface Clarification {
  id: string;
  project_id: string;
  // null when redacted for the owner on a still-sealed-and-open tender.
  service_provider_id: string | null;
  question: string;
  answer: string | null;
  shared_with_all: boolean;
  created_at: string;
  answered_at: string | null;
  service_provider_company_name: string | null;
}

export interface ProjectAmendment {
  id: string;
  project_id: string;
  amendment_number: number;
  summary: string;
  changed_fields: string;
  reason: string | null;
  deadline_extended: boolean;
  material?: boolean;
  created_by: string;
  created_at: string;
}

export interface PaymentOverrideRecord {
  id: string;
  granted_by: string;
  reason: string;
  created_at: string;
  revoked_by: string | null;
  revoked_at: string | null;
}

export interface AuditLogEntry {
  id: string;
  actor_id: string | null;
  action: string;
  previous_value: string | null;
  new_value: string | null;
  reason: string | null;
  created_at: string;
}

// Stage 3.4: what a service provider is asked to price, and the measurable
// items to price against (optional: a non-itemized requirement has none).
export type PricingBasis = "lump_sum" | "per_item";

export interface RequirementItem {
  id: string;
  position: number;
  description: string;
  quantity: string | null;
  unit: string | null;
  specification: string | null;
}
