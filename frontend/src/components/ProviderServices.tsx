import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ServiceProviderProfile } from "@/api/types";
import { useCategories } from "@/components/CategoryField";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { KUWAIT_GOVERNORATES } from "@/lib/location";

// Stage 3.9: what this provider offers and where, in the platform's terms.
// Requirements that match on type of work or governorate check this.
export function ProviderServicesPanel({ profile }: { profile: ServiceProviderProfile }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: categories = [] } = useCategories();
  const initial = () => ({ categories: profile.service_categories, governorates: profile.service_governorates });
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setValues(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify([profile.service_categories, profile.service_governorates])]);

  const dirty = JSON.stringify(values) !== JSON.stringify(initial());
  const toggle = (key: "categories" | "governorates", id: string, on: boolean) => {
    setSaved(false);
    setValues((v) => ({ ...v, [key]: on ? [...v[key], id] : v[key].filter((x) => x !== id) }));
  };

  const save = useMutation({
    mutationFn: () => apiFetch<ServiceProviderProfile>("/service-provider/services", { method: "PUT", body: values }),
    onSuccess: (data) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(["service-provider-profile"], data);
      queryClient.invalidateQueries({ queryKey: ["service-provider-feed"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("services.saveError")),
  });

  const box = "flex items-center gap-2 text-sm text-navy";
  return (
    <section id="services" className="bg-white border border-border rounded px-5 py-4 mb-8">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("services.heading")}</h2>
      <p className="text-xs text-steel-light mb-3">{t("services.hint")}</p>
      <ErrorBanner message={error} />
      <div className="grid sm:grid-cols-2 gap-5">
        <fieldset>
          <legend className="font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("services.categories")}</legend>
          {categories.length === 0 ? (
            <p className="text-sm text-steel-light">{t("services.noCategories")}</p>
          ) : (
            categories.map((c) => (
              <label key={c.id} className={box}>
                <input type="checkbox" checked={values.categories.includes(c.id)} onChange={(e) => toggle("categories", c.id, e.target.checked)} />
                {c.name}
              </label>
            ))
          )}
        </fieldset>
        <fieldset>
          <legend className="font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("services.governorates")}</legend>
          {KUWAIT_GOVERNORATES.map((g) => (
            <label key={g} className={box}>
              <input type="checkbox" checked={values.governorates.includes(g)} onChange={(e) => toggle("governorates", g, e.target.checked)} />
              {t(`location.${g}`)}
            </label>
          ))}
          <p className="text-xs text-steel-light mt-1">{t("services.allKuwait")}</p>
        </fieldset>
      </div>
      <div className="flex items-center gap-3 mt-4">
        <button type="button" onClick={() => save.mutate()} disabled={save.isPending || !dirty} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5">
          {t("services.save")}
        </button>
        {saved && !dirty && <span className="text-xs text-green">{t("services.saved")}</span>}
      </div>
    </section>
  );
}
