import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { AuditLogEntry, ServiceProviderProfile, PaymentOverrideRecord } from "@/api/types";
import { stars } from "@/lib/format";
import { DeleteServiceProviderForm } from "@/components/DeleteServiceProviderForm";
import { ErrorBanner } from "@/components/ErrorBanner";
import { PageLoading } from "@/components/PageLoading";

const STATUS_OPTIONS = ["incomplete", "pending_review", "changes_requested", "approved"] as const;

const MARKETPLACE_STATUS_LABEL: Record<string, string> = {
  documents_incomplete: "Documents incomplete",
  submitted_for_review: "Submitted for review",
  changes_requested: "Changes requested",
  payment_required: "Payment required",
  payment_restricted: "Payment restricted",
  verified_active: "Verified & active",
  suspended: "Suspended",
};

const MARKETPLACE_STATUS_BADGE: Record<string, string> = {
  documents_incomplete: "bg-blue-tint text-steel",
  submitted_for_review: "bg-amber/15 text-amber-dark",
  changes_requested: "bg-red-tint text-red",
  payment_required: "bg-amber/15 text-amber-dark",
  payment_restricted: "bg-red-tint text-red",
  verified_active: "bg-green-tint text-green",
  suspended: "bg-red-tint text-red",
};

function MarketplaceAccessPanel({ serviceProviderId, service_provider }: { serviceProviderId: string; service_provider: ServiceProviderProfile }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: overrides } = useQuery({
    queryKey: ["admin-payment-overrides", serviceProviderId],
    queryFn: () => apiFetch<PaymentOverrideRecord[]>(`/admin/service-providers/${serviceProviderId}/payment-overrides`),
  });

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-service-provider", serviceProviderId] });
    queryClient.invalidateQueries({ queryKey: ["admin-payment-overrides", serviceProviderId] });
    queryClient.invalidateQueries({ queryKey: ["admin-audit-log", serviceProviderId] });
  };

  const grantMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/service-providers/${serviceProviderId}/payment-override`, { method: "POST", body: { reason } }),
    onSuccess: () => {
      setReason("");
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not grant override."),
  });

  const revokeMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/service-providers/${serviceProviderId}/payment-override/revoke`, { method: "POST", body: { reason: reason || null } }),
    onSuccess: () => {
      setReason("");
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not revoke override."),
  });

  const label = MARKETPLACE_STATUS_LABEL[service_provider.marketplace_status] ?? service_provider.marketplace_status;
  const badge = MARKETPLACE_STATUS_BADGE[service_provider.marketplace_status] ?? "bg-blue-tint text-steel";

  return (
    <div className="bg-white border border-border rounded px-5 py-4.5">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">Marketplace access</h3>
      <div className="flex items-center gap-2 mb-3">
        <span className={`font-mono text-[10px] uppercase px-2.5 py-1 rounded-full ${badge}`}>{label}</span>
        {service_provider.payment_override_active && (
          <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-blue-tint text-blue">Admin override active</span>
        )}
      </div>
      <p className="text-[11.5px] text-steel-light mb-3">
        Subscription: {service_provider.subscription_status || "none"}
        {service_provider.subscription_current_period_end &&
          ` · renews ${new Date(service_provider.subscription_current_period_end).toLocaleDateString()}`}
      </p>

      <ErrorBanner message={error} />

      <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
        {service_provider.payment_override_active ? "Revoke reason (optional)" : "Override reason (required)"}
      </label>
      <textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={2}
        placeholder="Why is this override needed? This is recorded permanently."
        className="w-full border border-border rounded px-3 py-2 text-sm mb-2 resize-y"
      />
      {service_provider.payment_override_active ? (
        <button
          type="button"
          onClick={() => revokeMutation.mutate()}
          disabled={revokeMutation.isPending}
          className="bg-red-tint text-red text-xs font-semibold rounded px-4 py-2 disabled:opacity-60"
        >
          Revoke override
        </button>
      ) : (
        <button
          type="button"
          onClick={() => grantMutation.mutate()}
          disabled={grantMutation.isPending || !reason.trim()}
          className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-4 py-2 disabled:opacity-40"
        >
          Grant payment override
        </button>
      )}

      {!!overrides?.length && (
        <div className="mt-4 border-t border-border pt-3">
          <h4 className="font-mono text-[10px] uppercase tracking-wide text-steel mb-2">Override history</h4>
          <ul className="space-y-2">
            {overrides.map((o) => (
              <li key={o.id} className="text-[11.5px] text-steel">
                <span className="font-mono text-[10px] text-steel-light">{new Date(o.created_at).toLocaleString()}</span>
                {" — "}
                {o.reason}
                {o.revoked_at && <span className="text-red"> (revoked {new Date(o.revoked_at).toLocaleString()})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ActivityLogPanel({ serviceProviderId }: { serviceProviderId: string }) {
  const { data: entries } = useQuery({
    queryKey: ["admin-audit-log", serviceProviderId],
    queryFn: () => apiFetch<AuditLogEntry[]>(`/admin/service-providers/${serviceProviderId}/audit-log`),
  });

  if (!entries?.length) return null;

  return (
    <div className="bg-white border border-border rounded px-5 py-4.5">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">Activity log</h3>
      <ul className="space-y-2 max-h-64 overflow-y-auto">
        {entries.map((e) => (
          <li key={e.id} className="text-[11.5px] text-steel border-b border-border pb-2 last:border-0">
            <div className="font-mono text-[10px] text-steel-light">{new Date(e.created_at).toLocaleString()}</div>
            <div>
              <span className="font-semibold text-navy">{e.action}</span>
              {e.previous_value !== null && e.new_value !== null && (
                <span className="text-steel-light">
                  {" "}
                  ({e.previous_value} → {e.new_value})
                </span>
              )}
            </div>
            {e.reason && <div className="text-steel-light italic">"{e.reason}"</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AdminServiceProviderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: detail } = useQuery({
    queryKey: ["admin-service-provider", id],
    queryFn: () => apiFetch<{ service_provider: ServiceProviderProfile }>(`/admin/service-providers/${id}`),
    enabled: !!id,
  });
  const service_provider = detail?.service_provider;

  const [companyName, setCompanyName] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [primaryTrade, setPrimaryTrade] = useState("");
  const [serviceArea, setServiceArea] = useState("");
  const [statusValue, setStatusValue] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!service_provider) return;
    setCompanyName(service_provider.company_name);
    setLicenseNumber(service_provider.license_number ?? "");
    setPrimaryTrade(service_provider.primary_trade ?? "");
    setServiceArea(service_provider.service_area ?? "");
    setStatusValue(service_provider.verification_status);
  }, [service_provider?.user_id]);

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-service-provider", id] });
    queryClient.invalidateQueries({ queryKey: ["admin-service-providers"] });
  };
  const onMutationError = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.detail : fallback);

  const updateMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/service-providers/${id}`, {
        method: "PATCH",
        body: { company_name: companyName, license_number: licenseNumber || null, primary_trade: primaryTrade || null, service_area: serviceArea || null },
      }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not save changes."),
  });

  const statusMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/service-providers/${id}/verification-status`, { method: "POST", body: { status: statusValue } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not update verification status."),
  });

  const suspendMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/service-providers/${id}/suspend`, { method: "POST", body: { suspended: !service_provider?.is_suspended } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, "Could not update account access."),
  });

  if (!service_provider) return <PageLoading />;

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">Admin · Service providers</span>
      <div className="flex items-start justify-between flex-wrap gap-3 mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-navy mb-1">{service_provider.company_name}</h1>
          <p className="text-[13.5px] text-steel">
            <span className="text-amber">{stars(Number(service_provider.avg_rating))}</span>{" "}
            <span className="font-mono text-steel">({service_provider.review_count} reviews)</span>
          </p>
        </div>
        {service_provider.is_suspended && <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-red-tint text-red">Suspended</span>}
      </div>

      <ErrorBanner message={error} />

      <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-6 items-start">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateMutation.mutate();
          }}
          className="grid gap-4 bg-white border border-border rounded px-5 py-4.5"
        >
          <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy -mb-1">Company details</h3>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">Company name</label>
            <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} required className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">License number</label>
            <input value={licenseNumber} onChange={(e) => setLicenseNumber(e.target.value)} className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">Primary trade</label>
            <input value={primaryTrade} onChange={(e) => setPrimaryTrade(e.target.value)} className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">Service area</label>
            <input value={serviceArea} onChange={(e) => setServiceArea(e.target.value)} className="w-full border border-border rounded px-3 py-2 text-sm" />
          </div>
          <button type="submit" className="bg-navy hover:bg-navy-deep text-white font-semibold text-sm rounded px-4 py-2 w-fit">
            Save changes
          </button>
        </form>

        <div className="grid gap-4">
          <div className="bg-white border border-border rounded px-5 py-4.5">
            <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">Verification status</h3>
            <div className="flex items-center gap-2">
              <select value={statusValue} onChange={(e) => setStatusValue(e.target.value)} className="border border-border rounded px-2.5 py-2 text-sm flex-1">
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s.replace("_", " ")}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => statusMutation.mutate()}
                className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-3 py-2"
              >
                Update
              </button>
            </div>
            <p className="text-[11px] text-steel-light mt-2">Admin override — bypasses the per-document review flow. Use with care.</p>
          </div>

          <MarketplaceAccessPanel serviceProviderId={service_provider.user_id} service_provider={service_provider} />

          <div className="bg-white border border-border rounded px-5 py-4.5">
            <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">Account access</h3>
            <button
              type="button"
              onClick={() => suspendMutation.mutate()}
              className={`text-xs font-semibold rounded px-4 py-2 w-full ${service_provider.is_suspended ? "bg-green-tint text-green" : "bg-red-tint text-red"}`}
            >
              {service_provider.is_suspended ? "Reactivate account" : "Suspend account"}
            </button>
            <p className="text-[11px] text-steel-light mt-2">
              {service_provider.is_suspended
                ? "This service provider can't view projects, drawings, or submit offers until reactivated."
                : "Immediately blocks the service provider from the feed and offers, without deleting anything."}
            </p>
          </div>

          <ActivityLogPanel serviceProviderId={service_provider.user_id} />

          <div className="bg-white border border-red/30 rounded px-5 py-4.5">
            <h3 className="font-mono text-[11px] uppercase tracking-wide text-red mb-3">Danger zone</h3>
            <DeleteServiceProviderForm
              serviceProviderId={service_provider.user_id}
              companyName={service_provider.company_name}
              onDeleted={() => navigate("/admin/service-providers")}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
