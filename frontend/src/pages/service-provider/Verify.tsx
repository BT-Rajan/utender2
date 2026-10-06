import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ServiceProviderDocument, ServiceProviderProfile } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { StakeholderSection, useIdentity } from "@/components/Stakeholder";
import { VerificationChecklist, VerificationStateBanner, isVerificationEditable } from "@/components/VerificationChecklist";
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
      queryClient.invalidateQueries({ queryKey: ["service-provider-profile"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("service_provider.verify.uploadError")),
  });

  const submitMutation = useMutation({
    mutationFn: () => apiFetch("/service-provider/submit-for-review", { method: "POST", body: { company_name: companyName, license_number: licenseNumber || null } }),
    onSuccess: () => navigate("/service-provider/status"),
  });

  const { data: identity } = useIdentity();
  const established = !!identity?.stakeholder?.status.stakeholder_established;
  const editable = isVerificationEditable(profile?.verification_state);

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

      {profile && <VerificationStateBanner state={profile.verification_state} note={profile.verification_note} />}

      <ErrorBanner message={error} />
      {profile?.verification_status === "approved" && <p className="text-sm text-green mb-4 max-w-2xl">{t("verification.addLaterHint")}</p>}

      <form onSubmit={handleSubmit} className="mb-10 grid gap-4 max-w-2xl">
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

        <VerificationChecklist
          documents={docs ?? []}
          editable={editable}
          // Stage 3.9: once verified, optional qualifications can still be
          // added; each is reviewed on its own and access continues.
          canUpload={(d) => profile?.verification_status === "approved" && !profile.is_suspended && !d.requirement_is_required}
          onUpload={(requirementId, file) => uploadMutation.mutate({ requirementId, file })}
          labels={{
            document: t("service_provider.verify.document"),
            status: t("service_provider.verify.statusCol"),
            required: t("service_provider.verify.required"),
            optional: t("service_provider.verify.optional"),
          }}
        />

        <button
          type="submit"
          disabled={submitMutation.isPending || !established || !editable}
          className="mt-4 bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
        >
          {submitMutation.isPending ? t("service_provider.verify.submitting") : t("service_provider.verify.submit")}
        </button>
        {identity && !established && <p className="text-xs text-amber-dark">{t("stakeholder.mustEstablish")}</p>}
      </form>
    </main>
  );
}
