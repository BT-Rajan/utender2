import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ServiceProviderProfile, DocumentStatus } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ApplicationDecisionControls, DocumentDecisionControls, type DocumentDecision } from "@/components/AdminReviewControls";
import { QueryError } from "@/components/QueryError";

interface QueueDocument {
  id: string;
  requirement_id: string;
  status: DocumentStatus;
  submitted_at: string | null;
  expires_on: string | null;
  requirement_name: string | null;
  requirement_description: string | null;
  requirement_is_required: boolean | null;
  requirement_effective_from: string | null;
  requirement_requires_expiry: boolean | null;
  admin_note: string | null;
  url: string | null;
}

function isStale(d: QueueDocument): boolean {
  if (d.status !== "approved" || !d.submitted_at || !d.requirement_effective_from) return false;
  return new Date(d.requirement_effective_from) > new Date(d.submitted_at);
}

function expiryLabel(d: QueueDocument): { text: string; tone: "expired" | "soon" | "ok" } | null {
  if (d.status !== "approved" || !d.expires_on) return null;
  const days = Math.floor((new Date(d.expires_on).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
  if (days < 0) return { text: "Expired", tone: "expired" };
  if (days <= 30) return { text: `Expires in ${days}d`, tone: "soon" };
  return { text: `Expires ${new Date(d.expires_on).toLocaleDateString()}`, tone: "ok" };
}

interface QueueEntry {
  service_provider: ServiceProviderProfile;
  documents: QueueDocument[];
}

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

export function AdminReviewPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const {
    data: queue,
    isError: queueError,
    refetch: refetchQueue,
  } = useQuery({
    queryKey: ["admin-review-queue"],
    queryFn: () => apiFetch<QueueEntry[]>("/admin/review/queue"),
  });

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-review-queue"] });
  };
  const onMutationError = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.detail : fallback);

  const decisionMutation = useMutation({
    mutationFn: (vars: { serviceProviderId: string; requirementId: string } & DocumentDecision) =>
      apiFetch("/admin/review/documents", {
        method: "POST",
        body: {
          service_provider_id: vars.serviceProviderId,
          requirement_id: vars.requirementId,
          decision: vars.decision,
          note: vars.note ?? null,
          expires_on: vars.expires_on ?? null,
        },
      }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not record that decision."),
  });

  const approveMutation = useMutation({
    mutationFn: (serviceProviderId: string) => apiFetch(`/admin/review/service-providers/${serviceProviderId}/approve`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not approve this service provider."),
  });

  const applicationMutation = useMutation({
    mutationFn: (vars: { serviceProviderId: string; action: "request-changes" | "reject"; note: string }) =>
      apiFetch(`/admin/review/service-providers/${vars.serviceProviderId}/${vars.action}`, { method: "POST", body: { note: vars.note || null } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not record that decision."),
  });

  const active = selectedId ?? queue?.[0]?.service_provider.user_id ?? null;
  const selected = queue?.find((c) => c.service_provider.user_id === active);

  const requiredDocs = selected?.documents.filter((d) => d.requirement_is_required) ?? [];
  const requiredApprovedCount = requiredDocs.filter((d) => d.status === "approved").length;
  const readyToApprove = requiredApprovedCount === requiredDocs.length;

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="mb-6">
        <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">Admin · Applications</span>
        <h1 className="font-display text-2xl font-semibold text-navy mb-1">Service provider applications</h1>
        <p className="text-[13.5px] text-steel">{queue?.length ?? 0} pending review{queue?.length === 1 ? "" : "s"}.</p>
      </div>

      <ErrorBanner message={error} />

      {queueError ? (
        <QueryError onRetry={() => refetchQueue()} />
      ) : !queue?.length ? (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel">No applications waiting on review.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[.9fr_1.6fr] gap-5 items-start">
          <div className="space-y-2.5">
            {queue.map((entry) => (
              <button
                key={entry.service_provider.user_id}
                type="button"
                onClick={() => setSelectedId(entry.service_provider.user_id)}
                className={`block w-full text-left px-4 py-3.5 border rounded ${
                  entry.service_provider.user_id === active ? "border-l-[3px] border-l-amber bg-blue-tint border-border" : "border-border bg-white"
                }`}
              >
                <div className="font-display font-semibold text-sm">{entry.service_provider.company_name}</div>
                <div className="font-mono text-[10.5px] text-steel mt-1">
                  {entry.service_provider.primary_trade || "Trade not set"} · Submitted{" "}
                  {new Date(entry.service_provider.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <div className="tblock rounded px-5.5 pt-5 pb-0">
              <div className="flex justify-between items-start gap-2 mb-1">
                <div>
                  <h3 className="font-display font-semibold text-lg">{selected.service_provider.company_name}</h3>
                  <p className="text-[12.5px] text-steel">{selected.service_provider.primary_trade || "Trade not set"}</p>
                </div>
                <span
                  className={`font-mono text-[10px] uppercase px-2.5 py-1 rounded-full ${statusBadge(
                    selected.service_provider.verification_status === "pending_review" ? "pending" : selected.service_provider.verification_status
                  )}`}
                >
                  {selected.service_provider.verification_status.replace("_", " ")}
                </span>
              </div>

              <div className="divide-y divide-border mt-4">
                {selected.documents.map((d) => (
                  <div key={d.id} className="py-3.5 flex justify-between items-start gap-3">
                    <div>
                      <div className="font-display font-semibold text-[13.5px]">{d.requirement_name}</div>
                      {d.url ? (
                        <a href={d.url} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-blue underline">
                          View document
                        </a>
                      ) : (
                        <div className="text-[11.5px] text-steel-light mt-0.5">
                          Not submitted {d.requirement_is_required ? "" : "— optional"}
                        </div>
                      )}
                      {isStale(d) && (
                        <div className="font-mono text-[10px] text-amber-dark mt-1">
                          ⚠ requirement changed since this was approved — consider re-review
                        </div>
                      )}
                      {expiryLabel(d) && (
                        <div
                          className={`font-mono text-[10px] mt-1 ${
                            expiryLabel(d)!.tone === "expired" ? "text-red" : expiryLabel(d)!.tone === "soon" ? "text-amber-dark" : "text-steel-light"
                          }`}
                        >
                          {expiryLabel(d)!.text}
                        </div>
                      )}
                    </div>
                    <div className="flex-shrink-0">
                      {d.status === "approved" && (
                        <span className="font-mono text-[10px] uppercase px-2 py-1 rounded-full bg-green-tint text-green">Approved</span>
                      )}
                      {d.status === "not_submitted" && !d.requirement_is_required && (
                        <span className="font-mono text-[10px] uppercase px-2 py-1 rounded-full bg-border text-steel">N/A</span>
                      )}
                      {d.status === "pending" && (
                        <DocumentDecisionControls
                          requiresExpiry={!!d.requirement_requires_expiry}
                          pending={decisionMutation.isPending}
                          onDecide={(decision) =>
                            decisionMutation.mutate({ serviceProviderId: selected.service_provider.user_id, requirementId: d.requirement_id, ...decision })
                          }
                        />
                      )}
                      {d.status === "rejected" && (
                        <div className="text-end">
                          <span className="font-mono text-[10px] uppercase px-2 py-1 rounded-full bg-red-tint text-red">Correction requested</span>
                          {d.admin_note && <div className="text-[11px] text-red mt-1 max-w-[16rem]">{d.admin_note}</div>}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="py-4.5 border-t border-border mt-1">
                <ApplicationDecisionControls
                  canApprove={readyToApprove}
                  pending={approveMutation.isPending || applicationMutation.isPending}
                  onApprove={() => approveMutation.mutate(selected.service_provider.user_id)}
                  onRequestChanges={(note) => applicationMutation.mutate({ serviceProviderId: selected.service_provider.user_id, action: "request-changes", note })}
                  onReject={(note) => applicationMutation.mutate({ serviceProviderId: selected.service_provider.user_id, action: "reject", note })}
                />
              </div>
              {!readyToApprove && (
                <p className="text-[11px] text-steel-light -mt-2 pb-4">
                  All required documents must be approved before this service provider can be approved.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </main>
  );
}
