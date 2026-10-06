import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { AdminProject, OwnerDocument, OwnerProfile } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ApplicationDecisionControls, DocumentDecisionControls, type DocumentDecision } from "@/components/AdminReviewControls";
import { StakeholderSummary, type Stakeholder } from "@/components/Stakeholder";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { useState } from "react";

function statusBadge(status: string) {
  switch (status) {
    case "approved":
      return "bg-green-tint text-green";
    case "rejected":
      return "bg-red-tint text-red";
    case "pending":
      return "bg-amber/15 text-amber-dark";
    default:
      return "bg-blue-tint text-steel";
  }
}

export function AdminOwnerDetailPage() {
  const { t } = useI18n();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: detail } = useQuery({
    queryKey: ["admin-owner", id],
    queryFn: () => apiFetch<{ owner: OwnerProfile; stakeholder: Stakeholder; documents: OwnerDocument[] }>(`/admin/owners/${id}`),
    enabled: !!id,
  });

  const { data: projects } = useQuery({
    queryKey: ["admin-owner-projects", id],
    queryFn: () => apiFetch<AdminProject[]>(`/admin/owners/${id}/projects`),
    enabled: !!id,
  });

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-owner", id] });
    queryClient.invalidateQueries({ queryKey: ["admin-owners"] });
  };
  const onMutationError = (err: unknown, fallback: string) => setError(err instanceof ApiError ? err.detail : fallback);

  const reviewDocMutation = useMutation({
    mutationFn: ({ requirementId, decision, note, expires_on }: { requirementId: string } & DocumentDecision) =>
      apiFetch("/admin/review/owner-documents", {
        method: "POST",
        body: { owner_id: id, requirement_id: requirementId, decision, note: note ?? null, expires_on: expires_on ?? null },
      }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.ownerDetail.docReviewError")),
  });

  const approveMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/review/owners/${id}/approve`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.ownerDetail.approveError")),
  });

  const applicationMutation = useMutation({
    mutationFn: ({ action, note }: { action: "request-changes" | "reject"; note: string }) =>
      apiFetch(`/admin/review/owners/${id}/${action}`, { method: "POST", body: { note: note || null } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.ownerDetail.rejectError")),
  });

  const suspendMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/owners/${id}/suspend`, { method: "POST", body: { suspended: !detail?.owner.is_suspended } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.ownerDetail.suspendError")),
  });

  const deleteMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/owners/${id}`, { method: "DELETE" }),
    onSuccess: () => navigate("/admin/owners"),
    onError: (err) => onMutationError(err, t("admin.ownerDetail.deleteError")),
  });

  if (!detail) return <PageLoading />;
  const { owner, documents } = detail;

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("admin.owners.eyebrow")}</span>
      <div className="flex items-start justify-between flex-wrap gap-3 mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-navy mb-1">{owner.full_name || owner.email}</h1>
          <p className="text-[13.5px] text-steel">{owner.email}</p>
        </div>
        {owner.is_suspended && <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-red-tint text-red">{t("admin.ownerDetail.suspended")}</span>}
      </div>

      <ErrorBanner message={error} />

      {detail?.stakeholder && (
        <div className="bg-white border border-border rounded px-5 py-4.5 mb-6">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">{t("stakeholder.adminHeading")}</h3>
          <StakeholderSummary stakeholder={detail.stakeholder} viewerIsAdmin />
        </div>
      )}

      <div className="grid gap-4">
        <div className="bg-white border border-border rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">{t("admin.ownerDetail.documentsHeading")}</h3>
          <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2">{t("admin.ownerDetail.document")}</th>
                <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2">{t("admin.ownerDetail.statusCol")}</th>
                <th className="border-b-2 border-navy py-2"></th>
              </tr>
            </thead>
            <tbody>
              {documents.map((d) => (
                <tr key={d.id} className="border-b border-border">
                  <td className="py-3">
                    <div className="font-display font-semibold text-[13.5px]">{d.requirement_name}</div>
                    {d.url && (
                      <a href={d.url} target="_blank" rel="noreferrer" className="text-[11.5px] text-navy underline">
                        View document
                      </a>
                    )}
                    {d.admin_note && <div className="text-[11px] text-red">{d.admin_note}</div>}
                  </td>
                  <td className="py-3">
                    <span className={`font-mono text-[10px] uppercase px-2 py-1 rounded-full ${statusBadge(d.status)}`}>{d.status.replace("_", " ")}</span>
                  </td>
                  <td className="py-3">
                    {d.status === "pending" && (
                      <DocumentDecisionControls
                        requiresExpiry={!!d.requirement_requires_expiry}
                        pending={reviewDocMutation.isPending}
                        onDecide={(decision) => reviewDocMutation.mutate({ requirementId: d.requirement_id, ...decision })}
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>

        <div className="bg-white border border-border rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">{t("admin.ownerDetail.applicationHeading")}</h3>
          <p className="text-[11.5px] text-steel-light mb-3">
            {t("admin.ownerDetail.currentStatus")}: <span className="font-mono uppercase">{t(`verification.state_${owner.verification_state}`)}</span>
          </p>
          {owner.verification_note && <p className="text-[12px] text-navy mb-3">{owner.verification_note}</p>}
          <ApplicationDecisionControls
            canApprove={owner.verification_status !== "approved" && documents.every((d) => !d.requirement_is_required || d.status === "approved")}
            pending={approveMutation.isPending || applicationMutation.isPending}
            onApprove={() => approveMutation.mutate()}
            onRequestChanges={(note) => applicationMutation.mutate({ action: "request-changes", note })}
            onReject={(note) => applicationMutation.mutate({ action: "reject", note })}
          />
        </div>

        <div className="bg-white border border-border rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">{t("admin.ownerDetail.accessHeading")}</h3>
          <button
            type="button"
            onClick={() => suspendMutation.mutate()}
            className={`text-xs font-semibold rounded px-4 py-2 w-full ${owner.is_suspended ? "bg-green-tint text-green" : "bg-red-tint text-red"}`}
          >
            {owner.is_suspended ? t("admin.ownerDetail.reactivate") : t("admin.ownerDetail.suspend")}
          </button>
          <p className="text-[11px] text-steel-light mt-2">
            {owner.is_suspended ? t("admin.ownerDetail.suspendedNote") : t("admin.ownerDetail.suspendNote")}
          </p>
        </div>

        <div className="bg-white border border-border rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">{t("admin.ownerDetail.projectsHeading")}</h3>
          {!projects?.length ? (
            <p className="text-[12.5px] text-steel-light">{t("admin.ownerDetail.noProjects")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2">{t("admin.ownerDetail.projectTitleCol")}</th>
                    <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2">{t("admin.ownerDetail.projectStatusCol")}</th>
                    <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2">{t("admin.ownerDetail.projectOffersCol")}</th>
                    <th className="border-b-2 border-navy py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((p) => (
                    <tr key={p.id} className="border-b border-border">
                      <td className="py-2.5">
                        <div className="font-display font-semibold text-[13px]">{p.title}</div>
                        {p.is_suspended && <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded-full bg-red-tint text-red">{t("admin.projects.suspendedBadge")}</span>}
                      </td>
                      <td className="py-2.5 font-mono text-[11px] uppercase text-steel">{p.status.replace(/_/g, " ")}</td>
                      <td className="py-2.5 font-mono text-sm text-navy">{p.offer_count}</td>
                      <td className="py-2.5">
                        <Link to={`/admin/projects/${p.id}`} className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-2.5 py-1">
                          {t("admin.ownerDetail.viewProject")}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="bg-white border border-red/30 rounded px-5 py-4.5">
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-red mb-3">{t("admin.ownerDetail.dangerZone")}</h3>
          <p className="text-[11.5px] text-steel-light mb-3">
            {owner.project_count > 0 ? t("admin.ownerDetail.deleteBlockedNote") : t("admin.ownerDetail.deleteNote")}
          </p>
          <button
            type="button"
            onClick={() => {
              if (confirm(t("admin.ownerDetail.deleteConfirm"))) deleteMutation.mutate();
            }}
            disabled={deleteMutation.isPending || owner.project_count > 0}
            className="bg-red text-white text-xs font-semibold rounded px-4 py-2 disabled:opacity-40"
          >
            {t("admin.ownerDetail.deleteAccount")}
          </button>
        </div>
      </div>
    </main>
  );
}
