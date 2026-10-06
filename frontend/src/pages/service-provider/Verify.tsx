import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ServiceProviderDocument, DocumentRequirement, ServiceProviderProfile } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { StakeholderSection, useIdentity } from "@/components/Stakeholder";
import { useI18n } from "@/i18n/I18nContext";

export function ServiceProviderVerifyPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [companyName, setCompanyName] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: profile } = useQuery({
    queryKey: ["service-provider-profile"],
    queryFn: () => apiFetch<ServiceProviderProfile>("/service-provider/profile"),
  });
  useEffect(() => {
    if (!profile) return;
    setCompanyName(profile.company_name ?? "");
    setLicenseNumber(profile.license_number ?? "");
  }, [profile]);

  const { data: requirements } = useQuery({
    queryKey: ["service-provider-requirements"],
    queryFn: () => apiFetch<DocumentRequirement[]>("/service-provider/requirements"),
  });
  const { data: docs } = useQuery({
    queryKey: ["service-provider-documents"],
    queryFn: () => apiFetch<ServiceProviderDocument[]>("/service-provider/documents"),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ requirementId, file }: { requirementId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch(`/service-provider/documents/${requirementId}/upload`, { method: "POST", formData: form });
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["service-provider-documents"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("service_provider.verify.uploadError")),
  });

  const submitMutation = useMutation({
    mutationFn: () => apiFetch("/service-provider/submit-for-review", { method: "POST", body: { company_name: companyName, license_number: licenseNumber || null } }),
    onSuccess: () => navigate("/service-provider/status"),
  });

  const { data: identity } = useIdentity();
  const established = !!identity?.stakeholder?.status.stakeholder_established;

  const statusFor = (requirementId: string) => docs?.find((d) => d.requirement_id === requirementId)?.status ?? "not_submitted";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await submitMutation.mutateAsync();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("service_provider.verify.submitError"));
    }
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-10">
      <span className="font-mono text-[11px] uppercase tracking-widest text-amber-dark block mb-2">{t("service_provider.verify.eyebrow")}</span>
      <h1 className="font-display text-2xl font-semibold text-navy mb-2">{t("service_provider.verify.heading")}</h1>
      <p className="text-sm text-steel mb-8">{t("service_provider.verify.description")}</p>

      <StakeholderSection />

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} className="mb-10 grid gap-4 max-w-md">
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("service_provider.verify.companyName")}</label>
          <input
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            required
            className="w-full border border-border rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("service_provider.verify.licenseNumber")}</label>
          <input
            value={licenseNumber}
            onChange={(e) => setLicenseNumber(e.target.value)}
            className="w-full border border-border rounded px-3 py-2 text-sm"
          />
        </div>

        <div className="overflow-x-auto">
        <table className="w-full border-collapse mt-4">
          <thead>
            <tr className="text-left">
              <th className="font-mono text-[10px] uppercase text-steel border-b-2 border-navy py-2">{t("service_provider.verify.document")}</th>
              <th className="font-mono text-[10px] uppercase text-steel border-b-2 border-navy py-2">{t("service_provider.verify.statusCol")}</th>
              <th className="border-b-2 border-navy py-2"></th>
            </tr>
          </thead>
          <tbody>
            {requirements?.map((req) => (
              <tr key={req.id} className="border-b border-border">
                <td className="py-3">
                  <div className="font-display font-semibold text-sm">{req.name}</div>
                  <div className="text-xs text-steel-light">{req.description}</div>
                  <span className="font-mono text-[9.5px] uppercase text-steel-light">
                    {req.is_required ? t("service_provider.verify.required") : t("service_provider.verify.optional")}
                  </span>
                </td>
                <td className="py-3 font-mono text-xs capitalize">{statusFor(req.id).replace("_", " ")}</td>
                <td className="py-3">
                  <label className="flex items-center gap-2">
                    <input
                      type="file"
                      required
                      className="text-xs"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) uploadMutation.mutate({ requirementId: req.id, file });
                      }}
                    />
                  </label>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>

        <button
          type="submit"
          disabled={submitMutation.isPending || !established}
          className="mt-4 bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
        >
          {submitMutation.isPending ? t("service_provider.verify.submitting") : t("service_provider.verify.submit")}
        </button>
        {identity && !established && <p className="text-xs text-amber-dark">{t("stakeholder.mustEstablish")}</p>}
      </form>
    </main>
  );
}
