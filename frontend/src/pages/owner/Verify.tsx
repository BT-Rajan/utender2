import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { OwnerDocument, OwnerProfile } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { StakeholderSection, useIdentity } from "@/components/Stakeholder";
import { VerificationChecklist, VerificationStateBanner, isVerificationEditable } from "@/components/VerificationChecklist";
import { useI18n } from "@/i18n/I18nContext";
import { useState } from "react";

export function OwnerVerifyPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: profile } = useQuery({
    queryKey: ["owner-profile"],
    queryFn: () => apiFetch<OwnerProfile>("/owner/profile"),
  });
  const { data: docs } = useQuery({
    queryKey: ["owner-documents"],
    queryFn: () => apiFetch<OwnerDocument[]>("/owner/documents"),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ requirementId, file }: { requirementId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return apiFetch(`/owner/documents/${requirementId}/upload`, { method: "POST", formData: form });
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["owner-documents"] });
      queryClient.invalidateQueries({ queryKey: ["owner-profile"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("owner.verify.uploadError")),
  });

  const submitMutation = useMutation({
    mutationFn: () => apiFetch("/owner/submit-for-review", { method: "POST" }),
    onSuccess: () => navigate("/owner/status"),
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
      setError(err instanceof ApiError ? err.detail : t("owner.verify.submitError"));
    }
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-10">
      <span className="font-mono text-[11px] uppercase tracking-widest text-amber-dark block mb-2">{t("owner.verify.eyebrow")}</span>
      <h1 className="font-display text-2xl font-semibold text-navy mb-2">{t("owner.verify.heading")}</h1>
      <p className="text-sm text-steel mb-8">{t("owner.verify.description")}</p>

      <StakeholderSection />

      {profile && <VerificationStateBanner state={profile.verification_state} note={profile.verification_note} />}

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} className="mb-10 grid gap-4 max-w-2xl">
        <VerificationChecklist
          documents={docs ?? []}
          editable={editable}
          onUpload={(requirementId, file) => uploadMutation.mutate({ requirementId, file })}
          labels={{
            document: t("owner.verify.document"),
            status: t("owner.verify.statusCol"),
            required: t("owner.verify.required"),
            optional: t("owner.verify.optional"),
          }}
        />

        <button
          type="submit"
          disabled={submitMutation.isPending || !established || !editable}
          className="mt-4 bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
        >
          {submitMutation.isPending ? t("owner.verify.submitting") : t("owner.verify.submit")}
        </button>
        {identity && !established && <p className="text-xs text-amber-dark">{t("stakeholder.mustEstablish")}</p>}
      </form>
    </main>
  );
}
