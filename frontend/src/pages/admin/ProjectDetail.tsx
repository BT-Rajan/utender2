import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { AdminOffer, AdminProjectDetail } from "@/api/types";
import { AdminAuditTrail } from "@/components/AdminAuditTrail";
import { AdminDecisionTrace } from "@/components/AdminDecisionTrace";
import { ProviderCheck, PublishCheck } from "@/components/AdminSupport";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";
import { localInputToUtcIso, toLocalInputValue } from "@/lib/dates";

const OFFER_STATUS_BADGE: Record<string, string> = {
  submitted: "bg-blue-tint text-blue",
  approved: "bg-green-tint text-green",
  rejected: "bg-border text-steel",
  withdrawn: "bg-border text-steel-light",
};

type AdminItems = NonNullable<AdminProjectDetail["items"]>;

function OfferRow({ offer, projectId, items, t, currentRevision }: { offer: AdminOffer; projectId: string; items: AdminItems | null; t: (k: string) => string; currentRevision: number }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState(offer.amount ?? "");
  const [timeline, setTimeline] = useState(offer.timeline_estimate ?? "");
  const [message, setMessage] = useState(offer.message ?? "");
  // Priced per item (Stage 3.4/3.8): corrections are to the rates; the server recomputes the total.
  const [rates, setRates] = useState<Record<string, string>>(
    Object.fromEntries((offer.item_prices ?? []).map((l) => [l.item_id, String(Number(l.rate))])),
  );
  const [error, setError] = useState<string | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-project", projectId] });
    queryClient.invalidateQueries({ queryKey: ["admin-projects"] });
    queryClient.invalidateQueries({ queryKey: ["admin-offers"] });
  };

  const editMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/offers/${offer.id}`, {
        method: "PATCH",
        body: items
          ? { item_prices: items.map((i) => ({ item_id: i.id, rate: rates[i.id] ?? "" })), timeline_estimate: timeline || null, message: message || null }
          : { amount, timeline_estimate: timeline || null, message: message || null },
      }),
    onSuccess: () => {
      setEditing(false);
      setError(null);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("admin.projectDetail.editOfferError")),
  });

  const suspendMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/offers/${offer.id}/suspend`, { method: "POST", body: { suspended: !offer.is_suspended } }),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("admin.projectDetail.suspendOfferError")),
  });

  const deleteMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/offers/${offer.id}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("admin.projectDetail.deleteOfferError")),
  });

  if (editing) {
    return (
      <tr className="border-b border-border bg-blue-tint/30">
        <td colSpan={5} className="py-3 px-2.5">
          <div className="text-[11.5px] font-mono uppercase tracking-wide text-steel mb-2">
            {t("admin.projectDetail.editOfferHeading")} — {offer.service_provider_company_name ?? "—"}
          </div>
          {error && <div className="text-[11.5px] text-red mb-2">{error}</div>}
          <div className="grid sm:grid-cols-3 gap-2 mb-2">
            {items ? (
              <div className="sm:col-span-3 grid gap-1">
                {items.map((i) => (
                  <label key={i.id} className="flex items-center gap-2 text-xs">
                    <span className="flex-1">
                      {i.position}. {i.description}
                      {i.quantity !== null && ` (${Number(i.quantity)} ${i.unit ?? ""})`}
                    </span>
                    <input
                      aria-label={`Rate ${i.position}`}
                      value={rates[i.id] ?? ""}
                      onChange={(e) => setRates((r) => ({ ...r, [i.id]: e.target.value }))}
                      type="number"
                      step="0.001"
                      min="0"
                      className="w-28 border border-border rounded px-2 py-1 text-sm"
                    />
                  </label>
                ))}
              </div>
            ) : (
              <div>
                <label className="block font-mono text-[10px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.amountFieldLabel")}</label>
                <input value={amount} onChange={(e) => setAmount(e.target.value)} type="number" step="0.001" min="0.001" className="w-full border border-border rounded px-2.5 py-1.5 text-sm" />
              </div>
            )}
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.timelineFieldLabel")}</label>
              <input value={timeline} onChange={(e) => setTimeline(e.target.value)} className="w-full border border-border rounded px-2.5 py-1.5 text-sm" />
            </div>
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.messageFieldLabel")}</label>
              <input value={message} onChange={(e) => setMessage(e.target.value)} className="w-full border border-border rounded px-2.5 py-1.5 text-sm" />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => editMutation.mutate()}
              disabled={editMutation.isPending}
              className="bg-navy hover:bg-navy-deep text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-40"
            >
              {t("admin.projectDetail.saveOffer")}
            </button>
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setError(null);
              }}
              className="border border-border text-steel text-xs font-semibold rounded px-3 py-1.5"
            >
              {t("admin.projectDetail.cancel")}
            </button>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-border">
      <td className="py-3 px-2.5">
        <div className="text-[13px]">{offer.service_provider_company_name ?? "—"}</div>
        {/* Stage 9.3: which version of the requirement it priced, and when it was submitted. */}
        <div className="font-mono text-[10px] text-steel">
          {t("trace.pricedOn").replace("{n}", String(offer.based_on_material_revision ?? 0))}
          {(offer.based_on_material_revision ?? 0) < currentRevision && <span className="text-amber-dark"> · {t("trace.earlierVersion")}</span>}
          {offer.submitted_at && ` · ${new Date(offer.submitted_at).toLocaleString()}`}
        </div>
        {offer.is_suspended && (
          <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded-full bg-red-tint text-red">
            {t("admin.projectDetail.offerSuspendedBadge")}
          </span>
        )}
      </td>
      <td className="py-3 px-2.5 font-mono font-semibold text-navy text-sm">{money(offer.amount)}</td>
      <td className="py-3 px-2.5 text-[12.5px] text-steel">{offer.timeline_estimate || "—"}</td>
      <td className="py-3 px-2.5">
        <span className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded-full ${OFFER_STATUS_BADGE[offer.status] ?? "bg-blue-tint text-steel"}`}>
          {offer.status}
        </span>
      </td>
      <td className="py-3 px-2.5">
        <div className="flex gap-1.5 flex-wrap justify-end">
          <button type="button" onClick={() => setEditing(true)} className="border border-navy text-navy text-xs font-semibold rounded px-2.5 py-1">
            {t("admin.projectDetail.edit")}
          </button>
          <button
            type="button"
            onClick={() => suspendMutation.mutate()}
            disabled={suspendMutation.isPending}
            className={`text-xs font-semibold rounded px-2.5 py-1 ${offer.is_suspended ? "bg-green-tint text-green" : "bg-amber/15 text-amber-dark"}`}
          >
            {offer.is_suspended ? t("admin.projectDetail.reactivateOffer") : t("admin.projectDetail.suspendOffer")}
          </button>
          <button
            type="button"
            onClick={() => {
              if (confirm(t("admin.projectDetail.deleteOfferConfirm"))) deleteMutation.mutate();
            }}
            disabled={deleteMutation.isPending}
            className="bg-red-tint text-red text-xs font-semibold rounded px-2.5 py-1"
          >
            {t("admin.projectDetail.deleteOffer")}
          </button>
        </div>
        {error && !editing && <div className="text-[11px] text-red mt-1 text-right">{error}</div>}
      </td>
    </tr>
  );
}

export function AdminProjectDetailPage() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: detail } = useQuery({
    queryKey: ["admin-project", id],
    queryFn: () => apiFetch<AdminProjectDetail>(`/admin/projects/${id}`),
    enabled: !!id,
  });
  const project = detail?.project;

  const [title, setTitle] = useState("");
  const [address, setAddress] = useState("");
  const [description, setDescription] = useState("");
  const [trade, setTrade] = useState("");
  const [bidDeadline, setBidDeadline] = useState("");

  useEffect(() => {
    if (!project) return;
    setTitle(project.title);
    setAddress(project.address);
    setDescription(project.description ?? "");
    setTrade(project.trade ?? "");
    setBidDeadline(toLocalInputValue(project.bid_deadline));
  }, [project?.id]);

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-project", id] });
    queryClient.invalidateQueries({ queryKey: ["admin-projects"] });
    queryClient.invalidateQueries({ queryKey: ["admin-offers"] });
  };
  const onMutationError = (err: unknown, fallback: string) => setError(err instanceof ApiError ? err.detail : fallback);

  const editMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/projects/${id}`, {
        method: "PATCH",
        body: {
          title,
          address,
          description: description || null,
          trade: trade || null,
          bid_deadline: localInputToUtcIso(bidDeadline),
        },
      }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.projectDetail.saveError")),
  });

  const suspendMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/projects/${id}/suspend`, { method: "POST", body: { suspended: !project?.is_suspended } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.projectDetail.suspendError")),
  });

  const deleteMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/projects/${id}`, { method: "DELETE" }),
    onSuccess: () => navigate("/admin/projects"),
    onError: (err) => onMutationError(err, t("admin.projectDetail.deleteError")),
  });

  if (!detail || !project) return <PageLoading />;
  const { offers } = detail;

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("admin.projectDetail.eyebrow")}</span>
      <div className="flex items-start justify-between flex-wrap gap-3 mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-navy mb-1">{project.title}</h1>
          <p className="text-[13.5px] text-steel">
            {project.owner_name || project.owner_email} · {project.address}
          </p>
        </div>
        {project.is_suspended && <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-red-tint text-red">{t("admin.projectDetail.suspended")}</span>}
      </div>

      <ErrorBanner message={error} />

      <div className="grid gap-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            editMutation.mutate();
          }}
          className="grid gap-4 bg-white border border-border rounded px-5 py-4.5"
        >
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy -mb-1">{t("admin.projectDetail.editHeading")}</h3>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.titleLabel")}</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} required className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.addressLabel")}</label>
            <input value={address} onChange={(e) => setAddress(e.target.value)} required className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.descriptionLabel")}</label>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className="w-full border border-border rounded px-3 py-2 text-sm resize-y" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.tradeLabel")}</label>
            <input value={trade} onChange={(e) => setTrade(e.target.value)} className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("admin.projectDetail.deadlineLabel")}</label>
            <input value={bidDeadline} onChange={(e) => setBidDeadline(e.target.value)} type="datetime-local" required className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <button type="submit" disabled={editMutation.isPending} className="bg-navy hover:bg-navy-deep disabled:opacity-40 text-white font-semibold text-sm rounded px-4 py-2 w-fit">
            {t("admin.projectDetail.saveChanges")}
          </button>
        </form>

        <div className="bg-white border border-border rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">{t("admin.projectDetail.accessHeading")}</h3>
          <button
            type="button"
            onClick={() => suspendMutation.mutate()}
            disabled={suspendMutation.isPending}
            className={`text-xs font-semibold rounded px-4 py-2 w-full ${project.is_suspended ? "bg-green-tint text-green" : "bg-red-tint text-red"}`}
          >
            {project.is_suspended ? t("admin.projectDetail.reactivate") : t("admin.projectDetail.suspend")}
          </button>
          <p className="text-[11px] text-steel-light mt-2">
            {project.is_suspended ? t("admin.projectDetail.suspendedNote") : t("admin.projectDetail.suspendNote")}
          </p>
        </div>

        <AdminDecisionTrace projectId={id!} detail={detail} />
        <AdminAuditTrail url={`/admin/projects/${id}/audit`} />
        {/* Stage 9.4: support checks, from the same rules the marketplace enforces. */}
        {detail.project.status === "draft" && <PublishCheck projectId={id!} />}
        {detail.project.status === "open" && <ProviderCheck projectId={id!} />}

        <div className="bg-white border border-border rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">
            {t("admin.projectDetail.offersHeading")} ({offers.length})
          </h3>
          {!offers.length ? (
            <p className="text-[12.5px] text-steel-light">{t("admin.projectDetail.noOffers")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("admin.projectDetail.serviceProviderCol")}</th>
                    <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("admin.projectDetail.amountCol")}</th>
                    <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("admin.projectDetail.timelineCol")}</th>
                    <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">{t("admin.projectDetail.statusCol")}</th>
                    <th className="border-b-2 border-navy py-2 px-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {offers.map((o) => (
                    <OfferRow key={o.id} offer={o} projectId={id!} items={detail.pricing_basis === "per_item" ? detail.items ?? [] : null} t={t} currentRevision={detail.version?.material_revision ?? 0} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="bg-white border border-red/30 rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-red mb-3">{t("admin.projectDetail.dangerZone")}</h3>
          <p className="text-[11.5px] text-steel-light mb-3">
            {offers.length > 0 ? t("admin.projectDetail.deleteBlockedNote") : t("admin.projectDetail.deleteNote")}
          </p>
          <button
            type="button"
            onClick={() => {
              if (confirm(t("admin.projectDetail.deleteConfirm"))) deleteMutation.mutate();
            }}
            disabled={deleteMutation.isPending || offers.length > 0}
            className="bg-red text-white text-xs font-semibold rounded px-4 py-2 disabled:opacity-40"
          >
            {t("admin.projectDetail.deleteProject")}
          </button>
        </div>
      </div>
    </main>
  );
}
