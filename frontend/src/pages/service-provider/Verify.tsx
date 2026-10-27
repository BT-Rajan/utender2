import { useEffect, useState, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
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
  // Seeded once from the saved profile. Uploading a document refetches the
  // profile; re-seeding then would wipe a trading name or licence number the
  // provider had typed but not yet submitted (Stage 9.13).
  const seeded = useRef(false);
  // The saved trading name the field was last seeded with: while the provider
  // hasn't edited it, it follows the saved one -- set to the organization's
  // legal name when the account is set up as a company.
  const seededName = useRef<string | null>(null);
  useEffect(() => {
    if (!profile) return;
    const saved = profile.company_name ?? "";
    if (seeded.current) {
      const previous = seededName.current;  // read now: the updater may run after the ref moves on
      setCompanyName((typed) => (typed === previous ? saved : typed));
      seededName.current = saved;
      return;
    }
    seeded.current = true;
    seededName.current = saved;
    setCompanyName(saved);
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
    // Refetch first: the status page reads the same profile, and a cached "incomplete" one sends it straight back here.
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["service-provider-profile"] }),
        queryClient.invalidateQueries({ queryKey: ["service-provider-documents"] }),
        queryClient.invalidateQueries({ queryKey: ["verification-gate-profile"] }),
      ]);
      navigate("/service-provider/status");
    },
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
          <label htmlFor="sp-trading-name" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("service_provider.verify.companyName")}</label>
          <input
            id="sp-trading-name"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            required
            className="w-full border border-border rounded px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label htmlFor="sp-license-number" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">{t("service_provider.verify.licenseNumber")}</label>
          <input
            id="sp-license-number"
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

        {/* Under review: nothing to submit here -- point to where the application now stands. */}
        {profile?.verification_status === "pending_review" ? (
          <Link to="/service-provider/status" className="mt-4 text-sm text-blue underline w-fit" data-testid="see-status">{t("verification.submittedSeeStatus")}</Link>
        ) : <button
          type="submit"
          disabled={submitMutation.isPending || !established || !editable}
          className="mt-4 bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
        >
          {submitMutation.isPending ? t("service_provider.verify.submitting") : t("service_provider.verify.submit")}
        </button>}
        {identity && !established && <p className="text-xs text-amber-dark">{t("stakeholder.mustEstablish")}</p>}
      </form>
    </main>
  );
}
