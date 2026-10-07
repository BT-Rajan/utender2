import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError, draftVersion } from "@/api/client";
import type { PricingBasis, ProjectDetail, RequirementItem } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";

// Stage 3.4: the requirement's measurable pricing basis. Items are optional;
// the pricing basis says whether providers price the whole requirement or
// each item. PUT /projects/{id}/items saves both together.

// Suggestions only: the unit is free text.
const COMMON_UNITS = ["m", "m²", "m³", "nos", "kg", "ton", "L", "set", "lot", "day", "month", "visit"];

function formatQuantity(q: string | null): string {
  if (q === null) return "";
  const n = Number(q);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { maximumFractionDigits: 3 }) : q;
}

export function RequirementItemsView({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  if (project.pricing_basis === "lump_sum" && project.items.length === 0) return null;
  return (
    <div className="mb-6">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t("requirementItems.providerHeading")}</h3>
      <p className="text-sm text-navy mb-2">
        {t(`requirementItems.${project.pricing_basis}`)}
        <span className="text-steel"> · {t(`requirementItems.provider_${project.pricing_basis}`)}</span>
      </p>
      {project.items.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-start font-mono text-[10px] uppercase text-steel">
                <th className="border-b-2 border-navy py-2 pe-2 text-start">#</th>
                <th className="border-b-2 border-navy py-2 pe-2 text-start">{t("requirementItems.item")}</th>
                <th className="border-b-2 border-navy py-2 pe-2 text-end">{t("requirementItems.quantity")}</th>
                <th className="border-b-2 border-navy py-2 pe-2 text-start">{t("requirementItems.unit")}</th>
                <th className="border-b-2 border-navy py-2 text-start">{t("requirementItems.specification")}</th>
              </tr>
            </thead>
            <tbody>
              {project.items.map((item) => (
                <tr key={item.id} className="border-b border-border align-top">
                  <td className="py-2 pe-2 font-mono text-xs text-steel">{item.position}</td>
                  <td className="py-2 pe-2 text-navy">{item.description}</td>
                  <td className="py-2 pe-2 text-end font-mono">{item.quantity === null ? <span className="text-steel-light">{t("requirementItems.notSpecified")}</span> : formatQuantity(item.quantity)}</td>
                  <td className="py-2 pe-2">{item.unit}</td>
                  <td className="py-2 text-steel whitespace-pre-wrap break-words">{item.specification}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

interface Row {
  key: number;
  description: string;
  quantity: string;
  unit: string;
  specification: string;
}

let nextKey = 1;
const toRows = (items: RequirementItem[]): Row[] =>
  items.map((i) => ({
    key: nextKey++,
    description: i.description,
    quantity: i.quantity === null ? "" : String(Number(i.quantity)),
    unit: i.unit ?? "",
    specification: i.specification ?? "",
  }));
const blankRow = (): Row => ({ key: nextKey++, description: "", quantity: "", unit: "", specification: "" });

export function RequirementItemsEditor({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [basis, setBasis] = useState<PricingBasis>(project.pricing_basis);
  const [rows, setRows] = useState<Row[]>(() => toRows(project.items));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setBasis(project.pricing_basis);
    setRows(toRows(project.items));
  }, [project.pricing_basis, project.items]);

  const update = (key: number, patch: Partial<Row>) => {
    setSaved(false);
    setRows((current) => current.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  };

  const save = useMutation({
    mutationFn: () =>
      apiFetch<ProjectDetail>(`/projects/${project.id}/items`, {
        headers: draftVersion(project),
        method: "PUT",
        body: {
          pricing_basis: basis,
          items: rows
            .filter((r) => r.description.trim() || r.quantity || r.unit.trim() || r.specification.trim())
            .map((r) => ({
              description: r.description,
              quantity: r.quantity === "" ? null : r.quantity,
              unit: r.unit || null,
              specification: r.specification || null,
            })),
        },
      }),
    onSuccess: (data) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(["project", project.id], data);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("requirementItems.saveError")),
  });

  const input = "w-full border border-border rounded px-2 py-1.5 text-sm";
  return (
    <section className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-4xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("requirementItems.heading")}</h2>
      <p className="text-[13px] text-steel mb-4">{t("requirementItems.intro")}</p>
      <ErrorBanner message={error} />

      <form
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <fieldset className="mb-4">
          <legend className="font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("requirementItems.basisLabel")}</legend>
          <div className="grid sm:grid-cols-2 gap-2">
            {(["lump_sum", "per_item"] as const).map((option) => (
              <label
                key={option}
                className={`flex gap-2.5 items-start border rounded px-3 py-2.5 cursor-pointer ${basis === option ? "border-navy bg-blue-tint" : "border-border"}`}
              >
                <input
                  type="radio"
                  name="pricing_basis"
                  checked={basis === option}
                  onChange={() => {
                    setSaved(false);
                    setBasis(option);
                  }}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm font-semibold text-navy">{t(`requirementItems.${option}`)}</span>
                  <span className="block text-xs text-steel">{t(`requirementItems.${option}_hint`)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <datalist id="requirement-units">
          {COMMON_UNITS.map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>

        {rows.length === 0 ? (
          <p className="text-sm text-steel mb-3">{t("requirementItems.noItems")}</p>
        ) : (
          <div className="overflow-x-auto mb-3">
            <table className="w-full border-collapse">
              <thead>
                <tr className="font-mono text-[10px] uppercase text-steel">
                  <th className="py-1.5 pe-2 text-start w-6">#</th>
                  <th className="py-1.5 pe-2 text-start min-w-[14rem]">{t("requirementItems.item")}</th>
                  <th className="py-1.5 pe-2 text-start w-28">{t("requirementItems.quantity")}</th>
                  <th className="py-1.5 pe-2 text-start w-24">{t("requirementItems.unit")}</th>
                  <th className="py-1.5 pe-2 text-start min-w-[14rem]">{t("requirementItems.specification")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, i) => (
                  <tr key={row.key} className="align-top">
                    <td className="py-1 pe-2 font-mono text-xs text-steel pt-3">{i + 1}</td>
                    <td className="py-1 pe-2">
                      <input
                        aria-label={`${t("requirementItems.item")} ${i + 1}`}
                        value={row.description}
                        onChange={(e) => update(row.key, { description: e.target.value })}
                        required
                        maxLength={500}
                        className={input}
                      />
                    </td>
                    <td className="py-1 pe-2">
                      <input
                        aria-label={`${t("requirementItems.quantity")} ${i + 1}`}
                        type="number"
                        min="0"
                        step="any"
                        value={row.quantity}
                        onChange={(e) => update(row.key, { quantity: e.target.value })}
                        className={input}
                      />
                    </td>
                    <td className="py-1 pe-2">
                      <input
                        aria-label={`${t("requirementItems.unit")} ${i + 1}`}
                        list="requirement-units"
                        value={row.unit}
                        onChange={(e) => update(row.key, { unit: e.target.value })}
                        maxLength={30}
                        className={input}
                      />
                    </td>
                    <td className="py-1 pe-2">
                      <textarea
                        aria-label={`${t("requirementItems.specification")} ${i + 1}`}
                        value={row.specification}
                        onChange={(e) => update(row.key, { specification: e.target.value })}
                        placeholder={t("requirementItems.specificationPlaceholder")}
                        rows={1}
                        maxLength={4000}
                        className={`${input} resize-y`}
                      />
                    </td>
                    <td className="py-1 pt-2.5">
                      <button
                        type="button"
                        onClick={() => {
                          setSaved(false);
                          setRows((current) => current.filter((r) => r.key !== row.key));
                        }}
                        className="text-xs text-red underline"
                      >
                        {t("requirementItems.remove")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setSaved(false);
              setRows((current) => [...current, blankRow()]);
            }}
            className="border border-navy text-navy text-sm font-semibold rounded px-4 py-2"
          >
            {t("requirementItems.addItem")}
          </button>
          <button type="submit" disabled={save.isPending} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2">
            {t("requirementItems.save")}
          </button>
          {saved && <span className="text-xs text-green">{t("requirementItems.saved")}</span>}
        </div>
      </form>
    </section>
  );
}
