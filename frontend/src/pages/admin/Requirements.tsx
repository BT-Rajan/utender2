import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { DocumentRequirement } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { QueryError } from "@/components/QueryError";
import { useI18n } from "@/i18n/I18nContext";

export function AdminRequirementsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isRequired, setIsRequired] = useState(true);
  const [scopeFilter, setScopeFilter] = useState<"contractor" | "owner">("contractor");
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; name: string; description: string } | null>(null);

  const {
    data: requirements,
    isError: requirementsError,
    refetch: refetchRequirements,
  } = useQuery({
    queryKey: ["admin-requirements"],
    queryFn: () => apiFetch<DocumentRequirement[]>("/admin/requirements"),
  });

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-requirements"] });
  };
  const onMutationError = (err: unknown, fallback: string) =>
    setError(err instanceof ApiError ? err.detail : fallback);

  const addMutation = useMutation({
    mutationFn: () =>
      apiFetch("/admin/requirements", {
        method: "POST",
        body: { name, description: description || null, is_required: isRequired, applies_to: scopeFilter },
      }),
    onSuccess: () => {
      setName("");
      setDescription("");
      setIsRequired(true);
      invalidate();
    },
    onError: (err) => onMutationError(err, t("admin.requirements.addError")),
  });

  const toggleRequiredMutation = useMutation({
    mutationFn: ({ id, value }: { id: string; value: boolean }) =>
      apiFetch(`/admin/requirements/${id}`, { method: "PATCH", body: { is_required: value } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.requirements.updateError")),
  });

  const editMutation = useMutation({
    mutationFn: (edit: { id: string; name: string; description: string }) =>
      apiFetch(`/admin/requirements/${edit.id}`, { method: "PATCH", body: { name: edit.name, description: edit.description } }),
    onSuccess: () => {
      setEditing(null);
      invalidate();
    },
    onError: (err) => onMutationError(err, t("admin.requirements.updateError")),
  });

  const removeMutation = useMutation({
    mutationFn: (id: string) => apiFetch(`/admin/requirements/${id}`, { method: "PATCH", body: { is_active: false } }),
    onSuccess: invalidate,
    onError: (err) => onMutationError(err, t("admin.requirements.removeError")),
  });

  const active = (requirements ?? []).filter((r) => r.is_active && r.applies_to === scopeFilter);

  return (
    <main className="max-w-3xl mx-auto px-5 py-10">
      <span className="font-mono text-[11px] uppercase tracking-widest text-amber-dark block mb-2">{t("admin.requirements.eyebrow")}</span>
      <h1 className="font-display text-2xl font-semibold text-navy mb-2">{t("admin.requirements.heading")}</h1>
      <p className="text-sm text-steel mb-6">{t("admin.requirements.description")}</p>

      <div className="inline-flex border border-navy rounded-full overflow-hidden mb-6">
        <button
          type="button"
          onClick={() => setScopeFilter("contractor")}
          className={`font-mono text-xs px-4 py-1.5 uppercase tracking-wide ${scopeFilter === "contractor" ? "bg-navy text-white" : "bg-white text-navy"}`}
        >
          {t("admin.requirements.forContractors")}
        </button>
        <button
          type="button"
          onClick={() => setScopeFilter("owner")}
          className={`font-mono text-xs px-4 py-1.5 uppercase tracking-wide border-s border-navy ${scopeFilter === "owner" ? "bg-navy text-white" : "bg-white text-navy"}`}
        >
          {t("admin.requirements.forOwners")}
        </button>
      </div>

      <ErrorBanner message={error} />
      {requirementsError && <QueryError onRetry={() => refetchRequirements()} />}

      {!active.length && (
        <p className="text-sm text-steel-light mb-4">{t("admin.requirements.emptyForScope")}</p>
      )}

      <div className="space-y-2.5">
        {active.map((req) => (
          <div key={req.id} className="flex items-center gap-4 bg-white border border-border rounded px-4 py-3.5">
            <button
              type="button"
              onClick={() => toggleRequiredMutation.mutate({ id: req.id, value: !req.is_required })}
              aria-pressed={req.is_required}
              aria-label={`${t("admin.requirements.toggleRequiredFor")} ${req.name}`}
              className={`w-9 h-5 rounded-full relative transition-colors ${req.is_required ? "bg-green" : "bg-border"}`}
            >
              <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all ${req.is_required ? "left-4" : "left-0.5"}`} />
            </button>

            {editing?.id === req.id ? (
              <form
                className="flex-1 grid gap-1.5"
                onSubmit={(e) => {
                  e.preventDefault();
                  editMutation.mutate(editing);
                }}
              >
                <input
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  required
                  aria-label={t("admin.requirements.namePlaceholder")}
                  className="border border-border rounded px-2.5 py-1.5 text-sm"
                />
                <input
                  value={editing.description}
                  onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                  placeholder={t("admin.requirements.descriptionPlaceholder")}
                  className="border border-border rounded px-2.5 py-1.5 text-xs"
                />
                <div className="flex gap-2">
                  <button type="submit" disabled={editMutation.isPending} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1">
                    {t("common.save")}
                  </button>
                  <button type="button" onClick={() => setEditing(null)} className="text-xs text-steel underline">
                    {t("common.cancel")}
                  </button>
                </div>
              </form>
            ) : (
              <div className="flex-1">
                <div className="font-display font-semibold text-sm">{req.name}</div>
                <div className="text-xs text-steel-light">{req.description}</div>
              </div>
            )}

            <span className="font-mono text-[9.5px] uppercase text-steel-light">
              {req.is_required ? t("admin.requirements.required") : t("admin.requirements.optional")}
            </span>

            {editing?.id !== req.id && (
              <button
                type="button"
                onClick={() => setEditing({ id: req.id, name: req.name, description: req.description ?? "" })}
                className="text-xs text-navy underline"
              >
                {t("admin.requirements.edit")}
              </button>
            )}

            <button
              type="button"
              onClick={() => removeMutation.mutate(req.id)}
              title={t("admin.requirements.removeTitle")}
              className="w-7 h-7 border border-border rounded text-red hover:bg-red-tint text-sm"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          addMutation.mutate();
        }}
        className="grid grid-cols-1 sm:grid-cols-[1fr_1.6fr_auto_auto] gap-2.5 items-center bg-blue-tint border border-dashed border-blue rounded px-4 py-3.5 mt-4"
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder={t("admin.requirements.namePlaceholder")}
          className="border border-border rounded px-2.5 py-2 text-sm"
        />
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("admin.requirements.descriptionPlaceholder")}
          className="border border-border rounded px-2.5 py-2 text-sm"
        />
        <label className="flex items-center gap-1.5 font-mono text-[11px] text-navy whitespace-nowrap">
          <input type="checkbox" checked={isRequired} onChange={(e) => setIsRequired(e.target.checked)} /> {t("admin.requirements.required")}
        </label>
        <button type="submit" className="bg-navy hover:bg-navy-deep text-white text-xs font-semibold rounded px-3 py-2 whitespace-nowrap">
          {scopeFilter === "owner" ? t("admin.requirements.addForOwners") : t("admin.requirements.addForContractors")}
        </button>
      </form>
    </main>
  );
}
