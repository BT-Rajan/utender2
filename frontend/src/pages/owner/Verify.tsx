import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { DocumentRequirement, OwnerDocument } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { StakeholderSection, useIdentity } from "@/components/Stakeholder";
import { useI18n } from "@/i18n/I18nContext";
import { useState } from "react";

export function OwnerVerifyPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const { data: requirements } = useQuery({
    queryKey: ["owner-requirements"],
    queryFn: () => apiFetch<DocumentRequirement[]>("/owner/requirements"),
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
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("owner.verify.uploadError")),
  });

  const submitMutation = useMutation({
    mutationFn: () => apiFetch("/owner/submit-for-review", { method: "POST" }),
    onSuccess: () => navigate("/owner/status"),
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
      setError(err instanceof ApiError ? err.detail : t("owner.verify.submitError"));
    }
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-10">
      <span className="font-mono text-[11px] uppercase tracking-widest text-amber-dark block mb-2">{t("owner.verify.eyebrow")}</span>
      <h1 className="font-display text-2xl font-semibold text-navy mb-2">{t("owner.verify.heading")}</h1>
      <p className="text-sm text-steel mb-8">{t("owner.verify.description")}</p>

      <StakeholderSection />

      <ErrorBanner message={error} />

      <form onSubmit={handleSubmit} className="mb-10 grid gap-4 max-w-md">
        <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="text-left">
              <th className="font-mono text-[10px] uppercase text-steel border-b-2 border-navy py-2">{t("owner.verify.document")}</th>
              <th className="font-mono text-[10px] uppercase text-steel border-b-2 border-navy py-2">{t("owner.verify.statusCol")}</th>
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
                    {req.is_required ? t("owner.verify.required") : t("owner.verify.optional")}
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
          {submitMutation.isPending ? t("owner.verify.submitting") : t("owner.verify.submit")}
        </button>
        {identity && !established && <p className="text-xs text-amber-dark">{t("stakeholder.mustEstablish")}</p>}
      </form>
    </main>
  );
}
