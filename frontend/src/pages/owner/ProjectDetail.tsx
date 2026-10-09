import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError, API_URL, draftVersion } from "@/api/client";
import type { Drawing, Offer, ProjectDetail } from "@/api/types";
import { formatDeadline, formatSize, fullDate, timeRemaining, stars } from "@/lib/format";
import { RatingInput } from "@/components/RatingInput";
import { ErrorBanner } from "@/components/ErrorBanner";
import { RequirementItemsEditor, RequirementItemsView } from "@/components/RequirementItems";
import { PageLoading } from "@/components/PageLoading";
import { ClarificationsPanel } from "@/components/ClarificationsPanel";
import { EvaluationNotes } from "@/components/EvaluationNotes";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";
import { formatWorkTiming } from "@/lib/dates";
import { DraftDates } from "@/components/DraftDates";
import { OfferResponseDetails, ResponseRequirementsEditor } from "@/components/ResponseRequirements";
import { ProviderEligibilityEditor } from "@/components/ProviderEligibility";
import { CategoryField } from "@/components/CategoryField";
import { TenderRulesEditor } from "@/components/TenderRules";
import { QualityCheck, type QualityReport } from "@/components/QualityCheck";
import { useConfirm } from "@/components/ConfirmDialog";
import { AgreementPanel } from "@/components/AgreementPanel";
import { ReceivedReview, ReviewResponse } from "@/components/ReceivedReview";
import { TrackRecord } from "@/components/TrackRecord";
import { ClosureOutcome, EndRequirement, StartAgain, outcomeLabel } from "@/components/ClosureOutcome";
import { AmendPublishedForm, AmendmentsList, PauseControl } from "@/components/PostPublication";
import { InvitePreviousProviders } from "@/components/PreviousProviders";
import { DOCUMENT_ACCEPT, DOCUMENT_CATEGORIES, sortDocuments } from "@/lib/documents";
import { KUWAIT_GOVERNORATES, formatArea } from "@/lib/location";

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

interface Review {
  id: string;
  project_id: string;
  rating: number;
  comment: string | null;
  created_at: string;
  response?: string | null;  // Stage 8.9: the provider's response, if any
  response_at?: string | null;
  hidden?: boolean;  // Stage 8.15: an admin hid this review
  revealed?: boolean;  // Batch C: sealed from the other side until both reviewed, or reveals_on
  reveals_on?: string | null;
}

// Stage 7.1: the award handover -- read from the permanent award record, the
// one authoritative statement of who was selected for this requirement.
interface AwardRecordView {
  id: string | null;
  offer_id: string | null;
  amount: string | null;
  created_at: string;
  service_provider_company_name: string | null;
  material_revision: number | null;
}

function AwardSummary({ projectId, currency }: { projectId: string; currency: string }) {
  const { t, language } = useI18n();
  const { data: award } = useQuery({
    queryKey: ["award", projectId],
    queryFn: () => apiFetch<AwardRecordView>(`/projects/${projectId}/award`),
  });
  if (!award) return null;
  return (
    <section className="bg-white border border-green border-l-4 rounded px-5 py-4 mb-5" data-testid="award-summary">
      <div className="font-mono text-[10.5px] uppercase tracking-widest text-green mb-1">{t("awardHandover.heading")}</div>
      <div className="font-display font-semibold text-navy" dir="auto">
        {t("awardHandover.to").replace("{provider}", award.service_provider_company_name ?? t("owner.projectDetail.theServiceProvider"))}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[13px] mt-2">
        <dt className="text-steel">{t("awardHandover.value")}</dt>
        <dd className="font-mono text-navy">{money(award.amount, currency)}</dd>
        <dt className="text-steel">{t("awardHandover.on")}</dt>
        <dd>{fullDate(award.created_at, language)}</dd>
        {award.material_revision != null && (
          <>
            <dt className="text-steel">{t("awardHandover.version")}</dt>
            <dd>{t("versions.version").replace("{n}", String(award.material_revision))}</dd>
          </>
        )}
        {award.id && (
          <>
            <dt className="text-steel">{t("awardHandover.reference")}</dt>
            <dd className="font-mono text-xs break-all" data-testid="award-reference">{award.id}</dd>
          </>
        )}
      </dl>
      {award.offer_id && (
        <Link to={`/owner/projects/${projectId}/offers/${award.offer_id}`} className="inline-block mt-2 font-mono text-xs text-blue underline">
          {t("awardHandover.view")}
        </Link>
      )}
    </section>
  );
}

// Stage 6.3: how many offers came in, and where each stands -- counted from
// the server's list, never kept in the page.
function InboxCounts({ offers, t }: { offers: Offer[]; t: (key: string) => string }) {
  const count = (pred: (o: Offer) => boolean) => offers.filter(pred).length;
  const active = count((o) => o.status === "submitted");
  const withdrawn = count((o) => o.status === "withdrawn");
  const revised = count((o) => o.status !== "withdrawn" && o.revision > 1);
  const shortlisted = count((o) => !!o.shortlisted);
  const parts = [
    t("owner.projectDetail.inboxReceived").replace("{n}", String(offers.length)),
    active > 0 && t("owner.projectDetail.inboxActive").replace("{n}", String(active)),
    withdrawn > 0 && t("owner.projectDetail.withdrawnCount").replace("{n}", String(withdrawn)),
    revised > 0 && t("owner.projectDetail.inboxRevised").replace("{n}", String(revised)),
    shortlisted > 0 && t("shortlist.count").replace("{n}", String(shortlisted)),
  ].filter(Boolean);
  // Stage 6.5: live offers made against different versions of the requirement
  // don't answer the same thing -- said plainly before any figures across them.
  const versions = [...new Set(offers.filter((o) => o.status !== "withdrawn").map((o) => o.based_on_material_revision ?? 0))].sort((a, b) => a - b);
  return (
    <>
      <p className="font-mono text-[11px] text-steel mb-3" data-testid="inbox-counts">
        {parts.join(" · ")}
      </p>
      {versions.length > 1 && (
        <p className="text-xs text-amber-dark mb-3" data-testid="inbox-mixed-versions">
          ⚠ {t("owner.projectDetail.mixedVersions").replace("{versions}", versions.map((v) => t("versions.version").replace("{n}", String(v))).join(", "))}
        </p>
      )}
    </>
  );
}

// Stage 6.1: the server's default page of the owner's offer list.
const OFFERS_PAGE = 200;

function EvaluationSummary({ offers, t }: { offers: Offer[]; t: (key: string) => string }) {
  const active = offers.filter((o) => o.status !== "withdrawn" && o.amount !== null);
  if (active.length < 2) return null;

  const amounts = active.map((o) => Number(o.amount));
  const low = Math.min(...amounts);
  const high = Math.max(...amounts);
  const avg = amounts.reduce((a, b) => a + b, 0) / amounts.length;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 mb-4">
      <div className="border border-border bg-white rounded px-3 py-2.5">
        <div className="font-display text-lg font-semibold text-navy leading-none">{money(low)}</div>
        <div className="font-mono text-[9.5px] uppercase tracking-wide text-steel mt-1">{t("owner.projectDetail.lowestBid")}</div>
      </div>
      <div className="border border-border bg-white rounded px-3 py-2.5">
        <div className="font-display text-lg font-semibold text-navy leading-none">
          {money(avg)}
        </div>
        <div className="font-mono text-[9.5px] uppercase tracking-wide text-steel mt-1">{t("owner.projectDetail.averageBid")}</div>
      </div>
      <div className="border border-border bg-white rounded px-3 py-2.5">
        <div className="font-display text-lg font-semibold text-steel leading-none">{money(high)}</div>
        <div className="font-mono text-[9.5px] uppercase tracking-wide text-steel mt-1">{t("owner.projectDetail.highestBid")}</div>
      </div>
    </div>
  );
}

function DrawingHistory({ projectId, t }: { projectId: string; t: (key: string) => string }) {
  const { data: history } = useQuery({
    queryKey: ["drawing-history", projectId],
    queryFn: () => apiFetch<Drawing[]>(`/projects/${projectId}/drawings/history`),
  });

  if (!history?.length) return <p className="mt-2 font-mono text-[10.5px] text-steel-light">{t("owner.projectDetail.noHistory")}</p>;

  return (
    <ul className="mt-2 space-y-1 border-t border-white/20 pt-2">
      {history.map((d) => (
        <li key={d.id} className={`font-mono text-[10.5px] ${d.is_current ? "text-white" : "text-white/40"}`}>
          v{d.revision} · {d.file_name} {d.is_current && t("owner.projectDetail.current")}{" "}
          {d.url && (
            <a href={d.url} target="_blank" rel="noreferrer" className="underline">
              {t("owner.projectDetail.view")}
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}

function statusBadgeClasses(status: string) {
  switch (status) {
    case "open":
      return "bg-green-tint text-green";
    case "awarded":
      return "bg-amber/15 text-amber-dark";
    case "closed":
    case "under_evaluation":
      return "bg-blue-tint text-blue";
    case "draft":
      return "bg-border text-steel";
    default:
      // no_award, canceled, expired
      return "bg-red-tint text-red";
  }
}

// Mirrors MAX_SCOPE_CHARS in backend/app/routers/projects.py.
const MAX_SCOPE_CHARS = 20000;

// Stage 3.12: the owner says outright whether providers need the documents
// to price (rather than the quality check guessing from the wording).
function DocumentsNeeded({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (value: boolean) =>
      apiFetch<ProjectDetail>(`/projects/${project.id}`, { method: "PATCH", body: { documents_required: value }, headers: draftVersion(project) }),
    onSuccess: (data) => {
      setError(null);
      queryClient.setQueryData(["project", project.id], data);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("draftDetails.saveError")),
  });
  return (
    <div className="mt-3">
      <label className="flex items-start gap-2 text-[12.5px] text-navy">
        <input
          type="checkbox"
          className="mt-0.5"
          checked={!!project.documents_required}
          disabled={save.isPending}
          onChange={(e) => save.mutate(e.target.checked)}
        />
        <span>
          {t("documents.neededToPrice")}
          <span className="block text-[11px] text-steel-light">{t("documents.neededToPriceHint")}</span>
        </span>
      </label>
      {error && <p className="text-[11px] text-red mt-1">{error}</p>}
    </div>
  );
}

// Stage 3.2: the requirement's basic identity -- what the work is and where --
// editable while it is still a private draft.
function DraftDetailsForm({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(project.title);
  const [trade, setTrade] = useState(project.trade ?? "");
  const [governorate, setGovernorate] = useState(project.governorate ?? "");
  const [area, setArea] = useState(project.area ?? "");
  const [address, setAddress] = useState(project.address ?? "");
  const [description, setDescription] = useState(project.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setTitle(project.title);
    setTrade(project.trade ?? "");
    setGovernorate(project.governorate ?? "");
    setArea(project.area ?? "");
    setAddress(project.address ?? "");
    setDescription(project.description ?? "");
  }, [project.title, project.trade, project.governorate, project.area, project.address, project.description]);

  const dirty =
    title !== project.title ||
    trade !== (project.trade ?? "") ||
    governorate !== (project.governorate ?? "") ||
    area !== (project.area ?? "") ||
    address !== (project.address ?? "") ||
    description !== (project.description ?? "");

  const save = useMutation({
    mutationFn: () => apiFetch<ProjectDetail>(`/projects/${project.id}`, {
        method: "PATCH",
        body: { title, trade, governorate, area, address, description },
        headers: draftVersion(project),
      }),
    onSuccess: (data) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(["project", project.id], data);
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("draftDetails.saveError")),
  });

  const field = "w-full border border-border rounded px-3 py-2.5 text-sm";
  const label = "block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5";
  const hint = "text-xs text-steel-light mt-1";
  return (
    <section id="section-details" className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-2xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("draftDetails.heading")}</h2>
      <p className="text-[13px] text-steel mb-4">{t("draftDetails.intro")}</p>
      <ErrorBanner message={error} />
      <form
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          setSaved(false);
          save.mutate();
        }}
      >
        <div>
          <label htmlFor="draft-title" className={label}>{t("draftDetails.title")}</label>
          <input id="draft-title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={255} className={field} />
          <p className={hint}>{t("draftDetails.titleHint")}</p>
        </div>
        <div>
          <label htmlFor="draft-trade" className={label}>{t("draftDetails.category")}</label>
          <CategoryField id="draft-trade" value={trade} onChange={setTrade} className={field} />
          <p className={hint}>{t("draftDetails.categoryHint")}</p>
        </div>
        <div>
          {/* Stage 3.5: where the work is. Governorate and area are shown in
              listings; the exact address only on the full requirement. */}
          <span className={label}>{t("draftDetails.location")}</span>
          <div className="grid sm:grid-cols-2 gap-3 mb-3">
            <div>
              <label htmlFor="draft-governorate" className="block text-xs text-steel mb-1">{t("location.governorate")}</label>
              <select id="draft-governorate" value={governorate} onChange={(e) => setGovernorate(e.target.value)} className={field}>
                <option value="">{t("location.chooseGovernorate")}</option>
                {KUWAIT_GOVERNORATES.map((g) => (
                  <option key={g} value={g}>
                    {t(`location.${g}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="draft-area" className="block text-xs text-steel mb-1">{t("location.area")}</label>
              <input id="draft-area" value={area} onChange={(e) => setArea(e.target.value)} maxLength={100} className={field} />
            </div>
          </div>
          <p className={`${hint} -mt-2 mb-3`}>{t("location.areaHint")}</p>
          <label htmlFor="draft-address" className="block text-xs text-steel mb-1">{t("location.address")}</label>
          <input id="draft-address" value={address} onChange={(e) => setAddress(e.target.value)} required maxLength={500} className={field} />
          <p className={hint}>{t("location.addressHint")}</p>
          <p className={hint}>{t("location.siteNotesHint")}</p>
        </div>
        {/* Stage 3.3: the scope of work, stored in the existing description
            field. Free text with optional guidance -- no rigid template. */}
        <div className="border-t border-border pt-4">
          <div className="flex items-end justify-between gap-3 mb-1">
            <label htmlFor="draft-description" className="font-display text-base font-semibold text-navy">
              {t("draftDetails.scopeHeading")}
            </label>
            <button
              type="button"
              onClick={() =>
                setDescription((current) => (current.trim() ? `${current.trimEnd()}\n\n${t("draftDetails.outline")}` : t("draftDetails.outline")))
              }
              className="text-xs text-navy underline"
            >
              {t("draftDetails.insertOutline")}
            </button>
          </div>
          <p className="text-[13px] text-steel mb-1">{t("draftDetails.scopeIntro")}</p>
          <p className={`${hint} mb-2`}>{t("draftDetails.scopeTopics")}</p>
          <textarea
            id="draft-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={14}
            maxLength={MAX_SCOPE_CHARS}
            className={`${field} resize-y font-[inherit] leading-relaxed`}
          />
          <p className={`${hint} text-end`}>
            {t("draftDetails.charCount").replace("{count}", description.length.toLocaleString()).replace("{max}", MAX_SCOPE_CHARS.toLocaleString())}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={save.isPending || !dirty}
            className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5 w-fit"
          >
            {save.isPending ? t("draftDetails.saving") : t("draftDetails.save")}
          </button>
          {saved && !dirty && <span className="text-xs text-green">{t("draftDetails.saved")}</span>}
        </div>
      </form>
    </section>
  );
}

export function OwnerProjectDetailPage() {
  const { t, language } = useI18n();
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [rating, setRating] = useState(0);
  // Stage 6.6: offers chosen for side-by-side comparison (live ones only).
  const [compare, setCompare] = useState<string[]>([]);
  const navigate = useNavigate();
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const drawingsFormRef = useRef<HTMLFormElement>(null);

  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => apiFetch<ProjectDetail>(`/projects/${id}`),
    enabled: !!id,
    // Stage 4.6: document links last an hour; refresh them -- but never under
    // a draft being edited.
    refetchInterval: (q) => (q.state.data && q.state.data.status !== "draft" ? 20 * 60 * 1000 : false),
    // Stage 6.3: back on the page, the requirement's state as it is now.
    refetchOnWindowFocus: (q) => !!q.state.data && q.state.data.status !== "draft",
  });

  const { data: offers, isPending: offersLoading, isError: offersError } = useQuery({
    queryKey: ["owner-offers", id],
    queryFn: () => apiFetch<Offer[]>(`/owner/projects/${id}/offers`),
    enabled: !!id,
    // Stage 6.3: the offers as the server now holds them -- a provider may
    // submit, revise or withdraw while the owner has the page open.
    refetchInterval: 60 * 1000,
    refetchOnWindowFocus: true,
  });

  const { data: existingReview } = useQuery({
    queryKey: ["owner-review", id],
    queryFn: () => apiFetch<Review | null>(`/owner/projects/${id}/review`),
    enabled: !!id && project?.status === "awarded",
  });

  const approvedOffer = offers?.find((o) => o.status === "approved");
  // Stage 8.1: a review rests on completed work -- the transaction closed by the
  // owner side's acceptance -- never on the award alone. Same query as the agreement panel.
  const { data: transaction } = useQuery({
    queryKey: ["agreement", id],
    queryFn: () => apiFetch<{ status: string }>(`/projects/${id}/agreement`),
    enabled: !!id && project?.status === "awarded",
    retry: false,
  });
  const reviewable = transaction?.status === "completed";

  // Batch B: an offer on an earlier version, or past its validity, is confirmed by its provider before it can be awarded.
  const [askedToConfirm, setAskedToConfirm] = useState<string[]>([]);
  const requestConfirmationMutation = useMutation({
    mutationFn: (offerId: string) => apiFetch(`/owner/projects/${id}/offers/${offerId}/request-confirmation`, { method: "POST" }),
    onSuccess: (_, offerId) => {
      setError(null);
      setAskedToConfirm((prev) => [...prev, offerId]);
    },
    onError: (err) => setError(errorMessage(err, t("owner.projectDetail.approveError"))),
  });

  const approveMutation = useMutation({
    mutationFn: ({ offerId }: { offerId: string }) => apiFetch(`/owner/projects/${id}/offers/${offerId}/approve`, { method: "POST", body: {} }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-offers", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
    },
    onError: (err) => {
      setError(errorMessage(err, t("owner.projectDetail.approveError")));
      // Stage 6.3: refused because things changed (e.g. the offer was withdrawn): show them as they are.
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-offers", id] });
    },
  });

  const addDrawingsMutation = useMutation({
    mutationFn: (formData: FormData) => apiFetch(`/projects/${id}/drawings`, { method: "POST", formData }),
    onSuccess: () => {
      setError(null);
      drawingsFormRef.current?.reset();
      queryClient.invalidateQueries({ queryKey: ["project", id] });
    },
    onError: (err) => setError(errorMessage(err, t("owner.projectDetail.drawingsError"))),
  });

  // Stage 3.6: re-label or remove a document while the requirement is a draft.
  const documentMutation = useMutation({
    mutationFn: ({ drawingId, change }: { drawingId: string; change: { category?: string; is_required?: boolean } | "remove" }) =>
      change === "remove"
        ? apiFetch(`/projects/${id}/drawings/${drawingId}`, { method: "DELETE" })
        : apiFetch(`/projects/${id}/drawings/${drawingId}`, { method: "PATCH", body: change }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["project", id] });
    },
    onError: (err) => setError(errorMessage(err, t("documents.saveError"))),
  });

  const reviewMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/owner/reviews`, {
        method: "POST",
        body: { project_id: id, service_provider_id: approvedOffer?.service_provider_id, rating, comment: comment || null },
      }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["owner-review", id] });
    },
    onError: (err) => {
      setError(errorMessage(err, t("owner.projectDetail.reviewError")));
      queryClient.invalidateQueries({ queryKey: ["owner-review", id] });  // Stage 8.3: show what is on record
    },
  });

  const confirm = useConfirm();
  const lifecycleMutation = useMutation({
    mutationFn: (action: "publish" | "close" | "start-evaluation" | "discard") =>
      apiFetch(`/owner/projects/${id}/${action}`, { method: "POST" }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
    },
    onError: (err) => setError(errorMessage(err, t("owner.projectDetail.statusError"))),
    // Stage 6.17: a refused close or start of evaluation (e.g. a colleague
    // already decided) shows the requirement as the server now holds it. Not
    // after a refused publish: a draft being edited is never reloaded under the owner.
    onSettled: (_data, error, action) => {
      if (!error || action === "publish" || action === "discard") return;
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-offers", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
    },
  });

  // Stage 3.12: the server's quality check, re-read after every save.
  const { data: quality } = useQuery({
    queryKey: ["quality", id, project?.version],
    queryFn: () => apiFetch<QualityReport>(`/projects/${id}/quality`),
    enabled: !!project && project.status === "draft" && !project.discarded_at,
  });

  if (!project) return <PageLoading />;
  // Stage 3.11: a discarded draft stays readable to its owner but is closed to changes.
  const editableDraft = project.status === "draft" && !project.discarded_at;

  const deadlinePassed = new Date(project.bid_deadline) < new Date();

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="flex items-start justify-between flex-wrap gap-4 mb-6">
        <div>
          <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{project.title}</span>
          <h1 className="font-display text-2xl font-semibold text-navy mb-1">{t("owner.projectDetail.reviewOffers")}</h1>
          <p className="text-[13.5px] text-steel">
            {formatArea(t, project.governorate, project.area)} — {project.address}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wide px-2.5 py-1 rounded-full bg-blue-tint text-steel">
            {project.tender_type === "sealed" ? t("owner.projectDetail.sealedBadge") : t("owner.projectDetail.ownerVisibleBadge")}
          </span>
          <span className={`font-mono text-[10px] uppercase tracking-wide px-2.5 py-1 rounded-full ${statusBadgeClasses(project.status)}`}>
            {outcomeLabel(t, project.status, project.closure_reason, project.transaction_status)}
          </span>
        </div>
      </div>

      <ErrorBanner message={error} />

      {/* Stage 3.11: where this draft stands. */}
      {editableDraft && project.updated_at && (
        <p className="text-[12.5px] text-steel mb-4">{t("draftDetails.lastSaved").replace("{date}", formatDeadline(project.updated_at))}</p>
      )}
      {project.status === "expired" && project.offer_count === 0 && (
        <div className="border border-border bg-border/30 rounded px-4 py-3 mb-6 text-sm text-steel max-w-2xl">
          {t("draftDetails.expired").replace("{date}", formatDeadline(project.bid_deadline))}
        </div>
      )}
      {project.published_at && project.status === "open" && (
        <p className="text-[12.5px] text-steel mb-4">
          {t("draftDetails.published").replace("{date}", formatDeadline(project.published_at)).replace("{deadline}", formatDeadline(project.bid_deadline))}
        </p>
      )}
      {/* Stage 3.18: an admin suspension overrides everything providers see. */}
      {project.is_suspended && (
        <div className="border border-red bg-red-tint rounded px-4 py-3 mb-6 text-sm text-red max-w-2xl" data-testid="admin-suspended">
          {t("closure.adminSuspended")}
        </div>
      )}
      {project.restarted_from_id && (
        <p className="text-[12.5px] text-steel mb-4" data-testid="restarted-from">
          {t("closure.restartedFrom")}{" "}
          <Link to={`/owner/projects/${project.restarted_from_id}`} className="text-blue underline">
            {t("closure.restartedFromLink")}
          </Link>
        </p>
      )}
      {project.discarded_at && (
        <div className="border border-border bg-border/30 rounded px-4 py-3 mb-6 text-sm text-steel max-w-2xl">
          {t("draftDetails.discarded").replace("{date}", formatDeadline(project.discarded_at))}
        </div>
      )}

      {editableDraft && <DraftDetailsForm project={project} />}
      {editableDraft && <DraftDates project={project} />}
      {editableDraft && <TenderRulesEditor project={project} />}
      {editableDraft && <RequirementItemsEditor project={project} />}
      {editableDraft && <ResponseRequirementsEditor project={project} />}
      {editableDraft && <ProviderEligibilityEditor project={project} />}

      {/* Stage 3.15: controlling the published requirement. */}
      {project.status === "open" && <PauseControl project={project} />}
      {project.status === "open" && <AmendPublishedForm project={project} />}
      {project.status === "open" && !project.paused_at && <InvitePreviousProviders projectId={project.id} />}
      {/* Stage 7.1: the award, as recorded -- who, which offer, what value, when, on which version. */}
      {project.status === "awarded" && <AwardSummary projectId={project.id} currency={project.currency} />}
      {project.status === "awarded" && <AgreementPanel projectId={project.id} />}
      {project.closed_at && project.status !== "open" && (
        <p className="text-[12.5px] text-steel mb-4">{t("postPub.closedEarly").replace("{date}", formatDeadline(project.closed_at))}</p>
      )}
      {project.published_at && <div className="max-w-2xl"><AmendmentsList projectId={project.id} /></div>}
      {editableDraft && <QualityCheck report={quality} />}
      {editableDraft && (
        <Link
          to={`/owner/projects/${project.id}/preview`}
          className="inline-block mb-4 border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-4 py-2"
        >
          {t("preview.open")}
        </Link>
      )}

      {(editableDraft ||
        project.status === "open" ||
        project.status === "closed" ||
        project.status === "under_evaluation") && (
        <div className="flex flex-wrap gap-2 mb-6">
          {editableDraft && (
            <button
              type="button"
              onClick={() => {
                // Stage 3.14: publishing is a deliberate step, never a stray click.
                const text = t("draftDetails.publishConfirm").replace("{title}", project.title).replace("{deadline}", formatDeadline(project.bid_deadline));
                const [title, ...body] = text.split("\n\n");
                void confirm({ title, body: body.join("\n\n"), confirmLabel: t("owner.projectDetail.publish") }).then(
                  (ok) => ok && lifecycleMutation.mutate("publish"),
                );
              }}
              // The server refuses anyway; this just says so up front.
              disabled={lifecycleMutation.isPending || !quality?.ready}
              title={quality && !quality.ready ? t("quality.publishBlocked") : undefined}
              className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white text-xs font-semibold rounded px-4 py-2"
            >
              {t("owner.projectDetail.publish")}
            </button>
          )}
          {project.status === "open" && (
            <button
              type="button"
              onClick={() =>
                void confirm({ title: t("postPub.closeConfirm"), body: t("postPub.closeConfirmBody"), confirmLabel: t("owner.projectDetail.closeEarly") }).then(
                  (ok) => ok && lifecycleMutation.mutate("close"),
                )
              }
              disabled={lifecycleMutation.isPending}
              className="border border-navy text-navy hover:bg-navy hover:text-white disabled:opacity-60 text-xs font-semibold rounded px-4 py-2"
            >
              {t("owner.projectDetail.closeEarly")}
            </button>
          )}
          {project.status === "closed" && (
            <button
              type="button"
              onClick={() => lifecycleMutation.mutate("start-evaluation")}
              disabled={lifecycleMutation.isPending}
              className="border border-navy text-navy hover:bg-navy hover:text-white disabled:opacity-60 text-xs font-semibold rounded px-4 py-2"
            >
              {t("owner.projectDetail.startEvaluation")}
            </button>
          )}
          {editableDraft && (
            <button
              type="button"
              onClick={() => {
                void confirm({ title: t("draftDetails.discardConfirm"), confirmLabel: t("draftDetails.discard"), tone: "danger" }).then(
                  (ok) => ok && lifecycleMutation.mutate("discard"),
                );
              }}
              disabled={lifecycleMutation.isPending}
              className="text-xs text-red underline disabled:opacity-60"
            >
              {t("draftDetails.discard")}
            </button>
          )}
        </div>
      )}

      {/* Stage 3.16: ending it without a U-Tender award -- and saying how it ended. */}
      {(project.status === "open" || project.status === "closed" || project.status === "under_evaluation") && <EndRequirement project={project} />}
      {(project.status === "canceled" || project.status === "no_award") && <ClosureOutcome project={project} />}
      {(project.status === "canceled" || project.status === "no_award" || project.status === "expired") && <StartAgain project={project} />}
      {/* Stage 8.11: the same need again, after a completed transaction -- a new draft, this one untouched. */}
      {project.status === "awarded" && reviewable && <StartAgain project={project} similar />}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.5fr] gap-6 items-start">
        <div>
          <div className="aspect-[4/3] bg-navy rounded flex flex-col items-center justify-center gap-2 text-white/60 font-mono text-xs text-center px-4">
            {project.drawings.length ? (
              <ul className="space-y-2">
                {sortDocuments(project.drawings).map((d) => (
                  <li key={d.id}>
                    {d.url ? (
                      <a href={d.url} target="_blank" rel="noreferrer" className="text-white underline">
                        {d.file_name}
                      </a>
                    ) : (
                      <span>{d.file_name}</span>
                    )}
                    {d.revision > 1 && <span className="text-white/50"> · v{d.revision}</span>}
                    {formatSize(d.size_bytes) && <span className="text-white/50"> · {formatSize(d.size_bytes)}</span>}
                    <span className="text-white/60">
                      {" "}
                      · {t(`documents.${d.category}`)} · {d.is_required ? t("documents.essential") : t("documents.supplementary")}
                    </span>
                    {editableDraft && (
                      <div className="flex flex-wrap items-center gap-2 mt-1 normal-case">
                        <select
                          aria-label={`${t("documents.typeLabel")}: ${d.file_name}`}
                          value={d.category}
                          onChange={(e) => documentMutation.mutate({ drawingId: d.id, change: { category: e.target.value } })}
                          className="bg-white text-navy rounded px-1.5 py-0.5 text-[11px]"
                        >
                          {DOCUMENT_CATEGORIES.map((c) => (
                            <option key={c} value={c}>
                              {t(`documents.${c}`)}
                            </option>
                          ))}
                        </select>
                        <label className="flex items-center gap-1 text-[11px] text-white/80">
                          <input
                            type="checkbox"
                            checked={d.is_required}
                            onChange={(e) => documentMutation.mutate({ drawingId: d.id, change: { is_required: e.target.checked } })}
                          />
                          {t("documents.essentialToggle")}
                        </label>
                        <button
                          type="button"
                          onClick={() => {
                            void confirm({ title: t("documents.removeConfirm"), confirmLabel: t("confirm.remove"), tone: "danger" }).then(
                              (ok) => ok && documentMutation.mutate({ drawingId: d.id, change: "remove" }),
                            );
                          }}
                          className="text-[11px] text-red-tint underline"
                        >
                          {t("documents.remove")}
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <span>{t("owner.projectDetail.noDrawings")}</span>
            )}
          </div>

          {project.drawings.length > 0 && (
            <a href={`${API_URL}/projects/${project.id}/drawings-zip`} className="mt-2.5 inline-block font-mono text-xs text-blue underline">
              {t("owner.projectDetail.downloadZip")} ({project.drawings.length})
            </a>
          )}
          <button
            type="button"
            onClick={() => setShowHistory((v) => !v)}
            className="mt-2.5 block font-mono text-xs text-steel underline"
          >
            {showHistory ? t("owner.projectDetail.hideHistory") : t("owner.projectDetail.viewHistory")}
          </button>
          {showHistory && <DrawingHistory projectId={project.id} t={t} />}

          {editableDraft && <DocumentsNeeded project={project} />}
          {/* Documents can be added only while the requirement is a draft or open (the server refuses otherwise). */}
          {(project.status === "draft" || project.status === "open") && (
          <form
            id="section-documents"
            ref={drawingsFormRef}
            hidden={!!project.discarded_at}
            onSubmit={(e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              // An unchecked checkbox is simply absent from FormData; send it explicitly.
              form.set("is_required", form.get("is_required") ? "true" : "false");
              addDrawingsMutation.mutate(form);
            }}
            className="mt-3.5 flex flex-wrap items-center gap-2"
          >
            <input type="file" name="drawings" multiple accept={DOCUMENT_ACCEPT} className="text-[11px] flex-1" />
            <select name="category" defaultValue="drawing" aria-label={t("documents.typeLabel")} className="border border-border rounded px-1.5 py-1 text-[11px]">
              {DOCUMENT_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`documents.${c}`)}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-[11px] text-navy">
              <input type="checkbox" name="is_required" defaultChecked />
              {t("documents.essential")}
            </label>
            <button
              type="submit"
              className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-3 py-1.5 whitespace-nowrap"
            >
              {t("owner.projectDetail.addDrawings")}
            </button>
          </form>
          )}
          <p className="text-[11px] text-steel-light mt-1.5">{t("documents.uploadHint")}</p>
          <p className="text-[10.5px] text-steel-light mt-1">{t("owner.projectDetail.zipHint")}</p>
          <div
            className={`mt-3.5 px-3.5 py-3 rounded font-mono text-xs border-l-[3px] ${
              deadlinePassed ? "bg-red-tint text-red border-red" : "bg-blue-tint text-blue border-blue"
            }`}
          >
            {/* Stage 9.13: a countdown only while offers are open -- once closed early, the time left means nothing. */}
            {project.status === "open" ? `⏱ ${timeRemaining(project.bid_deadline)} — ` : ""}{fullDate(project.bid_deadline, language)}
            {formatWorkTiming(t, project) && <div className="mt-1 text-steel">{formatWorkTiming(t, project)}</div>}
          </div>
          {project.description && (
            <div className="mt-4 text-sm text-steel">
              <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t("owner.projectDetail.scope")}</h3>
              <div className="whitespace-pre-wrap break-words">{project.description}</div>
            </div>
          )}
          {project.status !== "draft" && (
            <div className="mt-4">
              <RequirementItemsView project={project} />
            </div>
          )}
          <div className="mt-4">
            <ClarificationsPanel
              projectId={project.id}
              role="owner"
              qaOpen={project.tender_rules.questions_open}
              closesAt={project.tender_rules.questions_close_at}
            />
          </div>
        </div>

        <div>
          {/* Stage 6.1: a failed or pending load is never shown as "no offers". */}
          {offersError && !offers ? (
            <div role="alert" className="border border-dashed border-red rounded p-8 text-center text-sm text-red">
              {t("owner.projectDetail.offersLoadError")}
            </div>
          ) : offersLoading ? null : !offers?.length ? (
            <div className="border border-dashed border-border rounded p-8 text-center text-sm text-steel">
              {project.status === "open" ? t("owner.projectDetail.noOffersYet") : t("owner.projectDetail.noOffersReceived")}
            </div>
          ) : offers[0]?.sealed ? (
            <div className="border border-dashed border-blue bg-blue-tint rounded p-8 text-center">
              <div className="text-xl mb-2">🔒</div>
              <p className="text-sm text-navy font-semibold mb-1">
                {/* A withdrawn offer isn't one received for consideration. */}
                {offers.filter((o) => o.status !== "withdrawn").length} {t("owner.projectDetail.sealedBidsReceived")}
                {offers.some((o) => o.status === "withdrawn") && (
                  <span className="font-normal text-steel">
                    {" · "}
                    {t("owner.projectDetail.withdrawnCount").replace("{n}", String(offers.filter((o) => o.status === "withdrawn").length))}
                  </span>
                )}
              </p>
              <p className="text-[12.5px] text-steel max-w-sm mx-auto">{t("owner.projectDetail.sealedExplanation")}</p>
            </div>
          ) : (
            <>
              <InboxCounts offers={offers} t={t} />
              {(() => {
                // Only offers still live in the server's list stay selected.
                const chosen = compare.filter((cid) => offers.some((o) => o.id === cid && o.status !== "withdrawn"));
                return (
                  <button
                    type="button"
                    disabled={chosen.length < 2}
                    onClick={() => navigate(`/owner/projects/${project.id}/compare?${chosen.map((cid) => `ids=${encodeURIComponent(cid)}`).join("&")}`)}
                    className="mb-3 border border-navy text-navy disabled:opacity-50 text-xs font-semibold rounded px-3 py-1.5"
                    data-testid="compare-selected"
                  >
                    {t("compareOffers.compareSelected").replace("{n}", String(chosen.length))}
                  </button>
                );
              })()}
              <EvaluationSummary offers={offers} t={t} />
              <div className="overflow-x-auto">
              <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.serviceProviderCol")}</th>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.ratingCol")}</th>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.bidCol")}</th>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.timelineCol")}</th>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.statusCol")}</th>
                  <th className="border-b-2 border-navy py-2 px-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {offers.map((o) => (
                  <tr key={o.id} className={`border-b border-border ${o.status === "withdrawn" ? "opacity-60" : ""}`} data-testid="owner-offer-row">
                    <td className="py-3 px-2.5">
                      <div className="font-display font-semibold text-[13.5px]">
                        {o.service_provider_company_name ?? t("owner.projectDetail.serviceProviderCol")}
                        {/* Stage 8.12/8.14: its U-Tender track record and work with you -- for information, never an advantage. */}
                        <TrackRecord offer={o} />
                        {o.status === "submitted" && (o.based_on_material_revision ?? 0) < (project.material_revision ?? 0) && (
                          <span className="block font-mono text-[10px] uppercase text-amber-dark font-normal">{t("postPub.outdatedOwner")}</span>
                        )}
                        {/* Stage 3.17: which version of the requirement this offer priced. */}
                        {(project.material_revision ?? 0) > 0 && (
                          <span className="block font-mono text-[10px] text-steel font-normal" data-testid="offer-version">
                            {t("versions.pricedOn").replace("{n}", String(o.based_on_material_revision ?? 0))}
                          </span>
                        )}
                        {o.revision > 1 && (
                          <span className="text-steel-light font-normal">
                            {" "}
                            · {t("owner.projectDetail.revisedSuffix")}
                            {o.revision - 1}
                          </span>
                        )}
                      </div>
                      {o.submitted_at && (
                        <div className="font-mono text-[10px] text-steel mt-0.5">
                          {t("owner.projectDetail.submittedOn")} {fullDate(o.submitted_at, language)}
                        </div>
                      )}
                      {o.message && <div className="text-xs text-steel-light mt-0.5 max-w-xs">{o.message}</div>}
                      {o.status !== "withdrawn" && (
                        <label className="flex items-center gap-1 mt-1 font-mono text-[11px] text-steel">
                          <input
                            type="checkbox"
                            checked={compare.includes(o.id)}
                            onChange={(e) => setCompare((prev) => (e.target.checked ? [...prev, o.id] : prev.filter((x) => x !== o.id)))}
                            data-testid="compare-select"
                          />
                          {t("compareOffers.select")}
                        </label>
                      )}
                      {/* Stage 6.4: the whole offer, as submitted, on its own page. */}
                      {o.status !== "withdrawn" && (
                        <Link to={`/owner/projects/${project.id}/offers/${o.id}`} className="inline-block mt-1 font-mono text-[11px] text-blue underline" data-testid="owner-offer-open">
                          {t("ownerOffer.open")}
                        </Link>
                      )}
                      <OfferResponseDetails offer={o} project={project} />
                    </td>
                    <td className="py-3 px-2.5">
                      {/* Stage 8.7/8.14: no reviews reads as "none yet", never as 0 stars; an average comes with its count. */}
                      {o.service_provider_review_count ? (
                        <>
                          <span className="text-amber text-[11px] tracking-tight">{stars(Number(o.service_provider_avg_rating ?? 0))}</span>{" "}
                          <span className="font-mono text-[11px] text-steel">
                            {t("reputation.summary").replace("{avg}", Number(o.service_provider_avg_rating ?? 0).toFixed(1)).replace("{n}", String(o.service_provider_review_count))}
                          </span>
                        </>
                      ) : (
                        <span className="font-mono text-[11px] text-steel">{t("reputation.noReviews")}</span>
                      )}
                    </td>
                    <td className="py-3 px-2.5 font-mono font-semibold text-navy text-sm">
                      {money(o.amount, project.currency)}
                    </td>
                    {/* Batch B: the committed duration or completion date first; the free-text period otherwise. */}
                    <td className="py-3 px-2.5 font-mono text-xs" data-testid="owner-offer-timing">
                      {o.proposed_duration_days
                        ? t("offerTiming.days").replace("{n}", String(o.proposed_duration_days))
                        : o.proposed_completion_date
                          ? t("offerTiming.by").replace("{date}", fullDate(o.proposed_completion_date, language))
                          : o.timeline_estimate || "—"}
                    </td>
                    <td className="py-3 px-2.5">
                      {/* Stage 6.1: the offer's own status, as the server holds it. */}
                      <span
                        className={`font-mono text-[10px] uppercase px-2 py-1 rounded-full whitespace-nowrap ${
                          o.status === "approved" ? "bg-green-tint text-green" : o.status === "submitted" ? "bg-blue-tint text-blue" : "bg-border text-steel"
                        }`}
                        data-testid="owner-offer-status"
                      >
                        {o.status === "submitted" ? t("owner.projectDetail.offerReceived") : t(`feed.offer_${o.status}`)}
                      </span>
                      {o.status === "submitted" && o.valid_until && (
                        <span className={`block mt-1 font-mono text-[10px] whitespace-nowrap ${o.validity_lapsed ? "text-red" : "text-steel"}`} data-testid="owner-offer-validity">
                          {o.validity_lapsed ? t("offerValidity.lapsed") : t("offerValidity.until").replace("{date}", fullDate(o.valid_until, language))}
                        </span>
                      )}
                      {!!o.answers_since && (
                        <span className="block mt-1 font-mono text-[10px] text-amber-dark" data-testid="owner-offer-answers-since">
                          {t("offerValidity.answersSince").replace("{n}", String(o.answers_since))}
                        </span>
                      )}
                      {o.shortlisted && (
                        <span className="block mt-1 font-mono text-[10px] text-amber-dark whitespace-nowrap" data-testid="owner-offer-shortlisted">★ {t("shortlist.badge")}</span>
                      )}
                    </td>
                    <td className="py-3 px-2.5">
                      {o.status !== "submitted" ? null : (project.status === "closed" || project.status === "under_evaluation") &&
                        ((o.based_on_material_revision ?? 0) < (project.material_revision ?? 0) || o.validity_lapsed) ? (
                        askedToConfirm.includes(o.id) ? (
                          <span className="font-mono text-[10px] text-steel" data-testid="owner-offer-confirmation-asked">{t("offerValidity.asked")}</span>
                        ) : (
                          <div>
                            <button
                              type="button"
                              onClick={() => requestConfirmationMutation.mutate(o.id)}
                              disabled={requestConfirmationMutation.isPending}
                              className="border border-navy text-navy hover:bg-blue-tint disabled:opacity-60 text-xs font-semibold rounded px-3 py-1.5"
                              data-testid="owner-offer-request-confirmation"
                            >
                              {t("offerValidity.ask")}
                            </button>
                            <p className="font-mono text-[10px] text-steel-light mt-1 max-w-[12rem]">{t("offerValidity.askHint")}</p>
                          </div>
                        )
                      ) : project.status === "closed" || project.status === "under_evaluation" ? (
                        <button
                          type="button"
                          onClick={() => {
                            // Stage 6.13: a final decision -- said plainly, and confirmed first.
                            const name = o.service_provider_company_name ?? t("owner.projectDetail.theServiceProvider");
                            const body = t("award.confirmBody").replace("{provider}", name).replace("{amount}", money(o.amount, project.currency));
                            void confirm({ title: t("award.confirmTitle").replace("{provider}", name), body, confirmLabel: t("award.confirm") }).then(
                              (ok) => ok && approveMutation.mutate({ offerId: o.id }),
                            );
                          }}
                          disabled={approveMutation.isPending}
                          className="bg-navy hover:bg-navy-deep disabled:opacity-60 text-white text-xs font-semibold rounded px-3 py-1.5"
                        >
                          {t("owner.projectDetail.approve")}
                        </button>
                      ) : project.status === "open" ? (
                        <span className="font-mono text-[10px] text-steel-light">{t("owner.projectDetail.closeToAwardHint")}</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
              </table>
              </div>
              {offers.length >= OFFERS_PAGE && (
                <p className="font-mono text-[10px] text-steel mt-2">{t("owner.projectDetail.offersTruncated").replace("{n}", String(offers.length))}</p>
              )}
            </>
          )}
        </div>
      </div>

      {/* Stage 6.11: the owner side's own private notes on the requirement. */}
      {project.status !== "draft" && <EvaluationNotes projectId={project.id} />}

      {approvedOffer && (existingReview || reviewable) && (
        <div className="mt-8 max-w-xl">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">
            {t("owner.projectDetail.rateServiceProvider")} {approvedOffer.service_provider_company_name ?? t("owner.projectDetail.theServiceProvider")}
          </h3>
          {existingReview ? (
            <div className="bg-white border border-border rounded px-4.5 py-4">
              <span className="text-amber text-lg tracking-tight">{stars(existingReview.rating)}</span>
              {existingReview.comment && <p className="text-sm text-steel mt-2">{existingReview.comment}</p>}
              <p className="font-mono text-[10.5px] text-steel-light mt-2">
                {t("owner.projectDetail.submittedOn")} {new Date(existingReview.created_at).toLocaleDateString()}
              </p>
              {existingReview.hidden && <p className="text-xs text-amber-dark mt-1">{t("report.hiddenNote")}</p>}
              {existingReview.revealed === false && (
                <p className="text-xs text-steel mt-1" data-testid="review-sealed">
                  {t("review.sealed").replace("{date}", existingReview.reveals_on ? fullDate(existingReview.reveals_on, language, false) : "")}
                </p>
              )}
              <ReviewResponse response={existingReview.response} at={existingReview.response_at} label={t("review.theirResponse")} reportBase={`/owner/projects/${project.id}`} />
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                // Stage 8.3: a review is final -- confirm before it's recorded.
                void confirm({ title: t("review.confirmTitle"), body: t("review.confirmBody"), confirmLabel: t("owner.projectDetail.submitReview") }).then(
                  (ok) => ok && reviewMutation.mutate(),
                );
              }}
              className="bg-white border border-border rounded px-4.5 py-4 grid gap-3.5"
            >
              <RatingInput value={rating} onChange={setRating} />
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
                maxLength={2000}
                dir="auto"
                aria-label={t("owner.projectDetail.ratingPlaceholder")}
                placeholder={t("owner.projectDetail.ratingPlaceholder")}
                className="w-full border border-border rounded px-3 py-2.5 text-sm resize-y"
              />
              <button
                type="submit"
                disabled={!rating || reviewMutation.isPending}
                className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
              >
                {t("owner.projectDetail.submitReview")}
              </button>
            </form>
          )}
          {/* Stage 8.6: the winning provider's review of this owner side, once written. */}
          <ReceivedReview
            url={`/owner/projects/${project.id}/review/received`}
            from={approvedOffer.service_provider_company_name ?? t("owner.projectDetail.theServiceProvider")}
          />
        </div>
      )}
    </main>
  );
}
