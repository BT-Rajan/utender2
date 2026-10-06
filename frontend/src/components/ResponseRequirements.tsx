import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { Offer, ProjectDetail, ResponseRequirements } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";

// Stage 3.8: what a provider's offer must contain. The price itself is always
// required (as one total or a rate per item, from the Stage 3.4 pricing
// basis); the owner chooses whether the completion period and technical
// approach are required, which documents to attach and which declarations to
// confirm. The server checks every offer against these rules.

const withCurrency = (text: string, currency: string) => text.replace("{currency}", currency);

let nextKey = 1;
interface DocRow {
  key: number;
  name: string;
  required: boolean;
}
interface DeclRow {
  key: number;
  text: string;
}

export function ResponseRequirementsEditor({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const rules = project.response_requirements;
  const initial = () => ({
    completion_period: rules.completion_period,
    approach: rules.approach,
    documents: rules.documents.map((d): DocRow => ({ key: nextKey++, ...d })),
    declarations: rules.declarations.map((text): DeclRow => ({ key: nextKey++, text })),
  });
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setValues(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(rules)]);

  const payload = (): ResponseRequirements => ({
    completion_period: values.completion_period,
    approach: values.approach,
    documents: values.documents.filter((d) => d.name.trim()).map((d) => ({ name: d.name.trim(), required: d.required })),
    declarations: values.declarations.map((d) => d.text.trim()).filter(Boolean),
  });
  const dirty = JSON.stringify(payload()) !== JSON.stringify(rules);
  const set = (patch: Partial<typeof values>) => {
    setSaved(false);
    setValues((v) => ({ ...v, ...patch }));
  };

  const save = useMutation({
    mutationFn: () => apiFetch<ProjectDetail>(`/projects/${project.id}/response-requirements`, { method: "PUT", body: payload() }),
    onSuccess: (data) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(["project", project.id], data);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("response.saveError")),
  });

  const field = "border border-border rounded px-3 py-2 text-sm";
  const toggle = (name: "completion_period" | "approach") => (
    <label className="flex items-center justify-between gap-3 text-sm text-navy">
      {t(name === "approach" ? "response.approach" : "response.completionPeriod")}
      <select
        aria-label={t(name === "approach" ? "response.approach" : "response.completionPeriod")}
        value={values[name]}
        onChange={(e) => set({ [name]: e.target.value as "required" | "optional" })}
        className={field}
      >
        <option value="required">{t("response.required")}</option>
        <option value="optional">{t("response.optional")}</option>
      </select>
    </label>
  );

  return (
    <section className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-2xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("response.heading")}</h2>
      <p className="text-xs text-steel-light mb-3">{withCurrency(t("response.hint"), project.currency)}</p>
      <ErrorBanner message={error} />
      <form
        className="grid gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-2 max-w-md">
          {toggle("completion_period")}
          {toggle("approach")}
        </div>

        <fieldset className="border-t border-border pt-4">
          <legend className="font-display text-sm font-semibold text-navy pt-4">{t("response.documentsHeading")}</legend>
          <p className="text-xs text-steel-light mb-2">{t("response.documentsHint")}</p>
          <div className="grid gap-2">
            {values.documents.map((d, i) => (
              <div key={d.key} className="flex flex-wrap items-center gap-2">
                <input
                  aria-label={t("response.documentName")}
                  value={d.name}
                  maxLength={120}
                  onChange={(e) => set({ documents: values.documents.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })}
                  className={`${field} flex-1 min-w-[12rem]`}
                />
                <select
                  aria-label={t("response.required")}
                  value={d.required ? "required" : "optional"}
                  onChange={(e) =>
                    set({ documents: values.documents.map((x, j) => (j === i ? { ...x, required: e.target.value === "required" } : x)) })
                  }
                  className={field}
                >
                  <option value="required">{t("response.required")}</option>
                  <option value="optional">{t("response.optional")}</option>
                </select>
                <button type="button" onClick={() => set({ documents: values.documents.filter((_, j) => j !== i) })} className="text-xs text-red underline">
                  {t("response.remove")}
                </button>
              </div>
            ))}
          </div>
          {values.documents.length < 10 && (
            <button
              type="button"
              onClick={() => set({ documents: [...values.documents, { key: nextKey++, name: "", required: true }] })}
              className="mt-2 text-xs text-blue underline"
            >
              + {t("response.addDocument")}
            </button>
          )}
        </fieldset>

        <fieldset className="border-t border-border pt-4">
          <legend className="font-display text-sm font-semibold text-navy pt-4">{t("response.declarationsHeading")}</legend>
          <p className="text-xs text-steel-light mb-2">{t("response.declarationsHint")}</p>
          <div className="grid gap-2">
            {values.declarations.map((d, i) => (
              <div key={d.key} className="flex items-center gap-2">
                <input
                  aria-label={t("response.declarationText")}
                  value={d.text}
                  maxLength={500}
                  onChange={(e) => set({ declarations: values.declarations.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })}
                  className={`${field} flex-1`}
                />
                <button type="button" onClick={() => set({ declarations: values.declarations.filter((_, j) => j !== i) })} className="text-xs text-red underline">
                  {t("response.remove")}
                </button>
              </div>
            ))}
          </div>
          {values.declarations.length < 10 && (
            <button
              type="button"
              onClick={() => set({ declarations: [...values.declarations, { key: nextKey++, text: "" }] })}
              className="mt-2 text-xs text-blue underline"
            >
              + {t("response.addDeclaration")}
            </button>
          )}
        </fieldset>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={save.isPending || !dirty} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5 w-fit">
            {t("response.save")}
          </button>
          {saved && !dirty && <span className="text-xs text-green">{t("response.saved")}</span>}
        </div>
      </form>
    </section>
  );
}

// The provider's checklist, shown above the offer form.
export function ResponseRequirementsSummary({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const rules = project.response_requirements;
  const mark = (required: boolean) => (
    <span className={`font-mono text-[10px] uppercase ms-1.5 ${required ? "text-amber-dark" : "text-steel-light"}`}>
      {required ? t("response.required") : t("response.optional")}
    </span>
  );
  return (
    <div className="mb-6 bg-blue-tint/40 border border-border rounded px-4 py-3">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1.5">{t("response.whatToSubmit")}</h3>
      <ul className="text-sm text-navy list-disc ps-5 leading-[1.8]">
        <li>
          {withCurrency(t(project.pricing_basis === "per_item" ? "response.pricePerItem" : "response.priceTotal"), project.currency)}
          {mark(true)}
        </li>
        <li>
          {t("response.completionPeriod")}
          {mark(rules.completion_period === "required")}
        </li>
        <li>
          {t("response.approach")}
          {mark(rules.approach === "required")}
        </li>
        <li>
          {t("response.assumptions")}
          {mark(false)}
        </li>
        {rules.documents.map((d) => (
          <li key={d.name}>
            {d.name}
            {mark(d.required)}
          </li>
        ))}
        {rules.declarations.length > 0 && (
          <li>
            {t("response.declarations")} ({rules.declarations.length}){mark(true)}
          </li>
        )}
      </ul>
    </div>
  );
}

// The structured parts of one offer, for the owner (and the provider's own copy).
export function OfferResponseDetails({ offer, project }: { offer: Offer; project: ProjectDetail }) {
  const { t } = useI18n();
  const items = new Map(project.items.map((i) => [i.id, i]));
  const hasAny = (offer.item_prices?.length ?? 0) > 0 || offer.assumptions || offer.documents?.length || offer.declarations_accepted?.length;
  if (!hasAny) return null;
  return (
    <details className="mt-1.5 text-xs text-steel max-w-md">
      <summary className="cursor-pointer text-blue">{t("response.details")}</summary>
      <div className="grid gap-2 mt-1.5">
        {offer.item_prices && offer.item_prices.length > 0 && (
          <div>
            <div className="font-mono text-[10px] uppercase text-navy">{t("response.itemBreakdown")}</div>
            <table className="w-full text-xs">
              <tbody>
                {offer.item_prices.map((line) => {
                  const item = items.get(line.item_id);
                  return (
                    <tr key={line.item_id} className="border-b border-border">
                      <td className="py-1 pe-2">{item ? `${item.position}. ${item.description}` : line.item_id}</td>
                      <td className="py-1 pe-2 font-mono text-end whitespace-nowrap">
                        {item?.quantity != null ? `${Number(item.quantity)} ${item.unit ?? ""} × ${line.rate}` : line.rate}
                      </td>
                      <td className="py-1 font-mono text-end whitespace-nowrap">{money(line.line_total, project.currency)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {offer.assumptions && (
          <div>
            <div className="font-mono text-[10px] uppercase text-navy">{t("response.assumptions")}</div>
            <div className="whitespace-pre-wrap break-words">{offer.assumptions}</div>
          </div>
        )}
        {offer.documents && offer.documents.length > 0 && (
          <div>
            <div className="font-mono text-[10px] uppercase text-navy">{t("response.attachments")}</div>
            <ul>
              {offer.documents.map((d) => (
                <li key={d.id}>
                  {d.label}:{" "}
                  <a href={d.url} target="_blank" rel="noreferrer" className="text-blue underline">
                    {d.file_name}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
        {offer.declarations_accepted && offer.declarations_accepted.length > 0 && (
          <div className="text-green">✓ {t("response.declarationsConfirmed")}</div>
        )}
      </div>
    </details>
  );
}
