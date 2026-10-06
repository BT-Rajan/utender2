import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError, API_URL } from "@/api/client";
import type { Drawing, Offer, ProjectDetail } from "@/api/types";
import { timeRemaining, stars } from "@/lib/format";
import { RatingInput } from "@/components/RatingInput";
import { ErrorBanner } from "@/components/ErrorBanner";
import { RequirementItemsEditor, RequirementItemsView } from "@/components/RequirementItems";
import { PageLoading } from "@/components/PageLoading";
import { ClarificationsPanel } from "@/components/ClarificationsPanel";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";
import { formatWorkTiming } from "@/lib/dates";
import { DraftDates } from "@/components/DraftDates";
import { OfferResponseDetails, ResponseRequirementsEditor } from "@/components/ResponseRequirements";
import { ProviderEligibilityEditor } from "@/components/ProviderEligibility";
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
}

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
        <div className="font-display text-lg font-semibold text-green leading-none">{money(low)}</div>
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
    mutationFn: () => apiFetch<ProjectDetail>(`/projects/${project.id}`, { method: "PATCH", body: { title, trade, governorate, area, address, description } }),
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
    <section className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-2xl">
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
          <input id="draft-trade" value={trade} onChange={(e) => setTrade(e.target.value)} maxLength={100} className={field} />
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
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const drawingsFormRef = useRef<HTMLFormElement>(null);

  const { data: project } = useQuery({
    queryKey: ["project", id],
    queryFn: () => apiFetch<ProjectDetail>(`/projects/${id}`),
    enabled: !!id,
  });

  const { data: offers } = useQuery({
    queryKey: ["owner-offers", id],
    queryFn: () => apiFetch<Offer[]>(`/owner/projects/${id}/offers`),
    enabled: !!id,
  });

  const { data: existingReview } = useQuery({
    queryKey: ["owner-review", id],
    queryFn: () => apiFetch<Review | null>(`/owner/projects/${id}/review`),
    enabled: !!id && project?.status === "awarded",
  });

  const approvedOffer = offers?.find((o) => o.status === "approved");

  const approveMutation = useMutation({
    mutationFn: (offerId: string) => apiFetch(`/owner/projects/${id}/offers/${offerId}/approve`, { method: "POST" }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-offers", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
    },
    onError: (err) => setError(errorMessage(err, t("owner.projectDetail.approveError"))),
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
    onError: (err) => setError(errorMessage(err, t("owner.projectDetail.reviewError"))),
  });

  const lifecycleMutation = useMutation({
    mutationFn: (action: "publish" | "close" | "start-evaluation" | "no-award" | "cancel") =>
      apiFetch(`/owner/projects/${id}/${action}`, { method: "POST" }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
    },
    onError: (err) => setError(errorMessage(err, t("owner.projectDetail.statusError"))),
  });

  if (!project) return <PageLoading />;

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
            {project.status.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      <ErrorBanner message={error} />

      {project.status === "draft" && <DraftDetailsForm project={project} />}
      {project.status === "draft" && <DraftDates project={project} />}
      {project.status === "draft" && <RequirementItemsEditor project={project} />}
      {project.status === "draft" && <ResponseRequirementsEditor project={project} />}
      {project.status === "draft" && <ProviderEligibilityEditor project={project} />}

      {(project.status === "draft" ||
        project.status === "open" ||
        project.status === "closed" ||
        project.status === "under_evaluation") && (
        <div className="flex flex-wrap gap-2 mb-6">
          {project.status === "draft" && (
            <button
              type="button"
              onClick={() => lifecycleMutation.mutate("publish")}
              disabled={lifecycleMutation.isPending}
              className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white text-xs font-semibold rounded px-4 py-2"
            >
              {t("owner.projectDetail.publish")}
            </button>
          )}
          {project.status === "open" && (
            <button
              type="button"
              onClick={() => lifecycleMutation.mutate("close")}
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
          {(project.status === "closed" || project.status === "under_evaluation") && (
            <button
              type="button"
              onClick={() => lifecycleMutation.mutate("no-award")}
              disabled={lifecycleMutation.isPending}
              className="bg-red-tint text-red text-xs font-semibold rounded px-4 py-2"
            >
              {t("owner.projectDetail.markNoAward")}
            </button>
          )}
          <button
            type="button"
            onClick={() => lifecycleMutation.mutate("cancel")}
            disabled={lifecycleMutation.isPending}
            className="text-xs text-red underline disabled:opacity-60"
          >
            {t("owner.projectDetail.cancelProject")}
          </button>
        </div>
      )}

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
                    <span className="text-white/60">
                      {" "}
                      · {t(`documents.${d.category}`)} · {d.is_required ? t("documents.essential") : t("documents.supplementary")}
                    </span>
                    {project.status === "draft" && (
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
                            if (window.confirm(t("documents.removeConfirm"))) documentMutation.mutate({ drawingId: d.id, change: "remove" });
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

          <form
            ref={drawingsFormRef}
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
          <p className="text-[11px] text-steel-light mt-1.5">{t("documents.uploadHint")}</p>
          <p className="text-[10.5px] text-steel-light mt-1">{t("owner.projectDetail.zipHint")}</p>
          <div
            className={`mt-3.5 px-3.5 py-3 rounded font-mono text-xs border-l-[3px] ${
              deadlinePassed ? "bg-red-tint text-red border-red" : "bg-blue-tint text-blue border-blue"
            }`}
          >
            ⏱ {timeRemaining(project.bid_deadline)} — {new Date(project.bid_deadline).toLocaleString()}
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
            <ClarificationsPanel projectId={project.id} role="owner" />
          </div>
        </div>

        <div>
          {!offers?.length ? (
            <div className="border border-dashed border-border rounded p-8 text-center text-sm text-steel">
              {t("owner.projectDetail.noOffersYet")}
            </div>
          ) : offers[0]?.sealed ? (
            <div className="border border-dashed border-blue bg-blue-tint rounded p-8 text-center">
              <div className="text-xl mb-2">🔒</div>
              <p className="text-sm text-navy font-semibold mb-1">
                {offers.length} {t("owner.projectDetail.sealedBidsReceived")}
              </p>
              <p className="text-[12.5px] text-steel max-w-sm mx-auto">{t("owner.projectDetail.sealedExplanation")}</p>
            </div>
          ) : (
            <>
              <EvaluationSummary offers={offers} t={t} />
              <div className="overflow-x-auto">
              <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.serviceProviderCol")}</th>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.ratingCol")}</th>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.bidCol")}</th>
                  <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("owner.projectDetail.timelineCol")}</th>
                  <th className="border-b-2 border-navy py-2 px-2.5"></th>
                </tr>
              </thead>
              <tbody>
                {offers.map((o) => (
                  <tr key={o.id} className="border-b border-border">
                    <td className="py-3 px-2.5">
                      <div className="font-display font-semibold text-[13.5px]">
                        {o.service_provider_company_name ?? t("owner.projectDetail.serviceProviderCol")}
                        {o.revision > 1 && (
                          <span className="text-steel-light font-normal">
                            {" "}
                            · {t("owner.projectDetail.revisedSuffix")}
                            {o.revision - 1}
                          </span>
                        )}
                      </div>
                      {o.message && <div className="text-xs text-steel-light mt-0.5 max-w-xs">{o.message}</div>}
                      <OfferResponseDetails offer={o} project={project} />
                    </td>
                    <td className="py-3 px-2.5">
                      <span className="text-amber text-[11px] tracking-tight">{stars(Number(o.service_provider_avg_rating ?? 0))}</span>{" "}
                      <span className="font-mono text-[11px] text-steel">({o.service_provider_review_count ?? 0})</span>
                    </td>
                    <td className="py-3 px-2.5 font-mono font-semibold text-navy text-sm">
                      {money(o.amount, project.currency)}
                    </td>
                    <td className="py-3 px-2.5 font-mono text-xs">{o.timeline_estimate || "—"}</td>
                    <td className="py-3 px-2.5">
                      {project.status === "awarded" || project.status === "no_award" ? (
                        <span
                          className={`font-mono text-[10px] uppercase px-2 py-1 rounded-full ${
                            o.status === "approved" ? "bg-green-tint text-green" : "bg-border text-steel"
                          }`}
                        >
                          {o.status}
                        </span>
                      ) : project.status === "closed" || project.status === "under_evaluation" ? (
                        <button
                          type="button"
                          onClick={() => approveMutation.mutate(o.id)}
                          disabled={approveMutation.isPending}
                          className="bg-navy hover:bg-navy-deep disabled:opacity-60 text-white text-xs font-semibold rounded px-3 py-1.5"
                        >
                          {t("owner.projectDetail.approve")}
                        </button>
                      ) : (
                        <span className="font-mono text-[10px] text-steel-light">{t("owner.projectDetail.closeToAwardHint")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              </table>
              </div>
            </>
          )}
        </div>
      </div>

      {approvedOffer && (
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
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                reviewMutation.mutate();
              }}
              className="bg-white border border-border rounded px-4.5 py-4 grid gap-3.5"
            >
              <RatingInput value={rating} onChange={setRating} />
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
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
        </div>
      )}
    </main>
  );
}
