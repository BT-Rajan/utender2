import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError, draftVersion } from "@/api/client";
import { Link } from "react-router-dom";
import type { EligibilityQualification, EligibilityReason, ProjectDetail, ProviderEligibility } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";

// Stage 3.9: who may respond to this requirement, on top of platform
// verification. Qualifications come from the platform's own (admin-managed)
// list of provider documents; the server enforces the same rules.

export function ProviderEligibilityEditor({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const rules = project.provider_eligibility;
  const initial = () => ({
    provider_type: rules.provider_type,
    qualifications: rules.qualifications.map((q) => q.id),
    match_category: rules.match_category,
    match_governorate: rules.match_governorate,
  });
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const { data: options = [] } = useQuery({
    queryKey: ["eligibility-qualifications"],
    queryFn: () => apiFetch<EligibilityQualification[]>("/owner/eligibility-qualifications"),
  });

  useEffect(() => {
    setValues(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(rules)]);

  const dirty = JSON.stringify(values) !== JSON.stringify(initial());
  const set = (patch: Partial<typeof values>) => {
    setSaved(false);
    setValues((v) => ({ ...v, ...patch }));
  };

  const save = useMutation({
    mutationFn: () => apiFetch<ProjectDetail>(`/projects/${project.id}/eligibility`, { method: "PUT", body: values , headers: draftVersion(project) }),
    onSuccess: (data) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(["project", project.id], data);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("eligibility.saveError")),
  });

  return (
    <section id="section-eligibility" className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-2xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("eligibility.heading")}</h2>
      <p className="text-xs text-steel-light mb-3">{t("eligibility.hint")}</p>
      <ErrorBanner message={error} />
      <form
        className="grid gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <fieldset>
          <legend className="font-display text-sm font-semibold text-navy mb-1.5">{t("eligibility.providerType")}</legend>
          {(["any", "organization"] as const).map((type) => (
            <label key={type} className="flex items-center gap-2 text-sm text-navy">
              <input type="radio" name="provider_type" checked={values.provider_type === type} onChange={() => set({ provider_type: type })} />
              {t(type === "any" ? "eligibility.anyProvider" : "eligibility.organizationOnly")}
            </label>
          ))}
        </fieldset>

        <fieldset className="border-t border-border pt-4">
          <legend className="font-display text-sm font-semibold text-navy pt-4">{t("eligibility.matchingHeading")}</legend>
          <label className="flex items-start gap-2 text-sm text-navy">
            <input
              type="checkbox"
              className="mt-1"
              checked={values.match_category}
              disabled={!project.category_id && !values.match_category}
              onChange={(e) => set({ match_category: e.target.checked })}
            />
            <span>
              {t("eligibility.matchCategory").replace("{category}", project.trade ?? "—")}
              {!project.category_id && <span className="block text-xs text-steel-light">{t("eligibility.matchCategoryUnavailable")}</span>}
            </span>
          </label>
          <label className="flex items-start gap-2 text-sm text-navy mt-1.5">
            <input
              type="checkbox"
              className="mt-1"
              checked={values.match_governorate}
              disabled={!project.governorate && !values.match_governorate}
              onChange={(e) => set({ match_governorate: e.target.checked })}
            />
            <span>
              {t("eligibility.matchGovernorate").replace("{governorate}", project.governorate ? t(`location.${project.governorate}`) : "—")}
              {!project.governorate && <span className="block text-xs text-steel-light">{t("eligibility.matchGovernorateUnavailable")}</span>}
            </span>
          </label>
        </fieldset>

        <fieldset className="border-t border-border pt-4">
          <legend className="font-display text-sm font-semibold text-navy pt-4">{t("eligibility.qualificationsHeading")}</legend>
          <p className="text-xs text-steel-light mb-2">{t("eligibility.qualificationsHint")}</p>
          {options.length === 0 ? (
            <p className="text-sm text-steel-light">{t("eligibility.noQualifications")}</p>
          ) : (
            <div className="grid gap-1.5">
              {options.map((o) => (
                <label key={o.id} className="flex items-start gap-2 text-sm text-navy">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={values.qualifications.includes(o.id)}
                    disabled={!values.qualifications.includes(o.id) && values.qualifications.length >= 5}
                    onChange={(e) =>
                      set({
                        qualifications: e.target.checked
                          ? [...values.qualifications, o.id]
                          : values.qualifications.filter((id) => id !== o.id),
                      })
                    }
                  />
                  <span>
                    {o.name}
                    {o.description && <span className="block text-xs text-steel-light">{o.description}</span>}
                  </span>
                </label>
              ))}
            </div>
          )}
        </fieldset>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={save.isPending || !dirty} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5 w-fit">
            {t("eligibility.save")}
          </button>
          {saved && !dirty && <span className="text-xs text-green">{t("eligibility.saved")}</span>}
        </div>
      </form>
    </section>
  );
}

// One line for providers: the rules they were measured against.
export function eligibilitySummary(t: (key: string) => string, rules: ProviderEligibility): string {
  const parts = [
    ...(rules.provider_type === "organization" ? [t("eligibility.organizationOnly")] : []),
    ...(rules.match_category && rules.category ? [rules.category] : []),
    ...(rules.match_governorate && rules.governorate ? [t(`location.${rules.governorate}`)] : []),
    ...rules.qualifications.map((q) => q.name),
  ];
  return parts.length ? parts.join(" · ") : t("eligibility.openToAll");
}

export function reasonText(t: (key: string) => string, reason: EligibilityReason): string {
  return t(`eligibility.reason_${reason.code}`)
    .replace("{name}", reason.name ?? "")
    .replace("{date}", reason.date ? new Date(`${reason.date}T00:00:00`).toLocaleDateString() : "")
    .replace("{governorate}", reason.governorate ? t(`location.${reason.governorate}`) : "");
}

// Each reason in the viewer's language. Stage 4.5: what the provider can put
// right themselves (with where to do it) apart from conditions that mean the
// opportunity simply isn't for them.
export function IneligibleNotice({ reasons }: { reasons: EligibilityReason[] }) {
  const { t } = useI18n();
  const fixable = reasons.filter((r) => r.fixable);
  const fixed = reasons.filter((r) => !r.fixable);
  const fixServices = fixable.some((r) => r.code === "category_not_offered" || r.code === "governorate_not_served");
  const addQualification = fixable.some((r) => r.code === "qualification_missing" || r.code === "qualification_expired");
  const item = (r: EligibilityReason) => <li key={r.code + (r.name ?? "") + (r.governorate ?? "")}>{reasonText(t, r)}</li>;
  return (
    <div className="border border-amber-dark/40 bg-amber/10 rounded px-4 py-3 text-sm text-navy" data-testid="ineligible-notice">
      <strong className="font-display block mb-1">{t("eligibility.notEligible")}</strong>
      {fixed.length > 0 && (
        <>
          {fixable.length > 0 && <p className="text-[12px] font-semibold text-navy mt-1">{t("eligibility.notForYou")}</p>}
          <ul className="list-disc ps-5 text-[13px] text-steel">{fixed.map(item)}</ul>
        </>
      )}
      {fixable.length > 0 && (
        <>
          <p className="text-[12px] font-semibold text-navy mt-1.5">{t("eligibility.youCanFix")}</p>
          <ul className="list-disc ps-5 text-[13px] text-steel">{fixable.map(item)}</ul>
          <div className="flex gap-3 mt-1.5 text-xs">
            {fixServices && (
              <Link to="/service-provider/dashboard#services" className="text-blue underline">
                {t("eligibility.fixServices")}
              </Link>
            )}
            {addQualification && (
              <Link to="/service-provider/verify" className="text-blue underline">
                {t("eligibility.addQualification")}
              </Link>
            )}
          </div>
        </>
      )}
    </div>
  );
}
