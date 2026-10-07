import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { Offer, OfferDocument, ProjectDetail } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { OutdatedOfferNotice } from "@/components/PostPublication";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";

// The provider's offer form. Shared by the provider's page and the owner's
// preview (Stage 3.13), where it is shown read-only: the owner sees exactly
// the fields a provider will fill in -- the item rate table, the required
// fields, the requested documents, the declarations -- and nothing is sent.
export function OfferForm({ project, existingOffer, preview = false }: { project: ProjectDetail; existingOffer: Offer | null; preview?: boolean }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [timeline, setTimeline] = useState("");
  const [message, setMessage] = useState("");
  const [assumptions, setAssumptions] = useState("");
  const [rates, setRates] = useState<Record<string, string>>({});
  const [accepted, setAccepted] = useState<string[]>([]);

  useEffect(() => {
    if (existingOffer) {
      setAmount(existingOffer.amount === null ? "" : String(Number(existingOffer.amount)));
      setTimeline(existingOffer.timeline_estimate ?? "");
      setMessage(existingOffer.message ?? "");
      setAssumptions(existingOffer.assumptions ?? "");
      setRates(Object.fromEntries((existingOffer.item_prices ?? []).map((l) => [l.item_id, String(Number(l.rate))])));
      setAccepted(existingOffer.declarations_accepted ?? []);
    }
  }, [existingOffer]);

  // Stage 3.8: attachments the requirement asks for, one per requested label.
  const { data: myDocuments = [] } = useQuery({
    queryKey: ["my-offer-documents", project.id],
    queryFn: () => apiFetch<OfferDocument[]>(`/projects/${project.id}/offers/documents`),
    enabled: !preview,
  });
  const uploadMutation = useMutation({
    mutationFn: ({ label, file }: { label: string; file: File }) => {
      const formData = new FormData();
      formData.append("label", label);
      formData.append("file", file);
      return apiFetch<OfferDocument[]>(`/projects/${project.id}/offers/documents`, { method: "POST", formData });
    },
    onSuccess: (docs) => {
      setError(null);
      queryClient.setQueryData(["my-offer-documents", project.id], docs);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("response.uploadError")),
  });
  const removeDocument = useMutation({
    mutationFn: (documentId: string) => apiFetch(`/projects/${project.id}/offers/documents/${documentId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["my-offer-documents", project.id] }),
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("response.uploadError")),
  });

  const perItem = project.pricing_basis === "per_item";
  const clean = (v: string) => v.replace(/[^0-9.]/g, "");
  // Shown as a guide only; the server computes the authoritative total.
  const lineTotal = (rate: string, quantity: string | null) => {
    if (!clean(rate)) return null;
    const value = Number(clean(rate)) * (quantity === null ? 1 : Number(quantity));
    return Math.round(value * 1000) / 1000;
  };
  const itemTotal = project.items.reduce((sum, item) => sum + (lineTotal(rates[item.id] ?? "", item.quantity) ?? 0), 0) ?? 0;

  const submitMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/projects/${project.id}/offers`, {
        method: "POST",
        body: {
          amount: perItem ? null : clean(amount),
          item_prices: perItem ? project.items.map((item) => ({ item_id: item.id, rate: clean(rates[item.id] ?? "") })) : null,
          timeline_estimate: timeline || null,
          message: message || null,
          assumptions: assumptions || null,
          accepted_declarations: accepted,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-offer", project.id] });
      queryClient.invalidateQueries({ queryKey: ["service-provider-feed"] });
    },
  });

  const withdrawMutation = useMutation({
    mutationFn: () => apiFetch(`/projects/${project.id}/offers/withdraw`, { method: "POST" }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["my-offer", project.id] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("service_provider.offer.withdrawError")),
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await submitMutation.mutateAsync();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("service_provider.offer.submitError"));
    }
  }

  const rules = project.response_requirements;
  const rateLabel = t("response.rateCol").replace("{currency}", project.currency);
  const requiredMark = <span className="text-amber-dark"> *</span>;

  return (
    <>
      <ErrorBanner message={error} />
      {existingOffer && !preview && <OutdatedOfferNotice project={project} offer={existingOffer} />}
      <fieldset disabled={preview} className={preview ? "opacity-80" : undefined}>
        <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-6 items-start">
          <form onSubmit={handleSubmit} className="grid gap-[18px]">
            {perItem ? (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="font-mono text-[10px] uppercase text-steel">
                      <th className="border-b-2 border-navy py-2 pe-2 text-start">{t("requirementItems.item")}</th>
                      <th className="border-b-2 border-navy py-2 pe-2 text-end">{t("requirementItems.quantity")}</th>
                      <th className="border-b-2 border-navy py-2 pe-2 text-start">{rateLabel}</th>
                      <th className="border-b-2 border-navy py-2 text-end">{t("response.lineTotalCol")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {project.items.map((item) => (
                      <tr key={item.id} className="border-b border-border">
                        <td className="py-2 pe-2 text-navy">
                          {item.position}. {item.description}
                        </td>
                        <td className="py-2 pe-2 font-mono text-end whitespace-nowrap">
                          {item.quantity === null ? "—" : `${Number(item.quantity)} ${item.unit ?? ""}`}
                        </td>
                        <td className="py-2 pe-2">
                          <input
                            aria-label={`${rateLabel} ${item.position}`}
                            value={rates[item.id] ?? ""}
                            onChange={(e) => setRates((r) => ({ ...r, [item.id]: e.target.value }))}
                            required
                            inputMode="decimal"
                            className="w-28 border border-border rounded px-2 py-1.5 text-sm font-mono"
                          />
                        </td>
                        <td className="py-2 font-mono text-end whitespace-nowrap">{money(lineTotal(rates[item.id] ?? "", item.quantity), project.currency)}</td>
                      </tr>
                    ))}
                    <tr>
                      <td colSpan={3} className="py-2 pe-2 font-mono text-[11px] uppercase text-navy text-end">{t("response.total")}</td>
                      <td className="py-2 font-mono font-semibold text-navy text-end whitespace-nowrap">{money(itemTotal, project.currency)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <div>
                <label htmlFor="offer-amount" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">
                  {t("response.amount").replace("{currency}", project.currency)}
                </label>
                <input
                  id="offer-amount"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  required
                  inputMode="decimal"
                  placeholder="8,400.000"
                  className="w-full border border-border rounded px-3 py-2.5 text-sm font-mono"
                />
              </div>
            )}
            <div>
              <label htmlFor="offer-timeline" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">
                {t("response.completionPeriod")}
                {rules.completion_period === "required" && requiredMark}
              </label>
              <input
                id="offer-timeline"
                value={timeline}
                onChange={(e) => setTimeline(e.target.value)}
                required={rules.completion_period === "required"}
                placeholder={t("service_provider.offer.timelinePlaceholder")}
                className="w-full border border-border rounded px-3 py-2.5 text-sm"
              />
            </div>
            <div>
              <label htmlFor="offer-message" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">
                {t("response.approach")}
                {rules.approach === "required" && requiredMark}
              </label>
              <textarea
                id="offer-message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                required={rules.approach === "required"}
                rows={4}
                placeholder={t("service_provider.offer.messagePlaceholder")}
                className="w-full border border-border rounded px-3 py-2.5 text-sm resize-y"
              />
            </div>
            <div>
              <label htmlFor="offer-assumptions" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("response.assumptions")}</label>
              <textarea
                id="offer-assumptions"
                value={assumptions}
                onChange={(e) => setAssumptions(e.target.value)}
                rows={3}
                maxLength={10000}
                placeholder={t("response.assumptionsPlaceholder")}
                className="w-full border border-border rounded px-3 py-2.5 text-sm resize-y"
              />
            </div>
            {rules.documents.length > 0 && (
              <fieldset>
                <legend className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("response.attachments")}</legend>
                <ul className="grid gap-2">
                  {rules.documents.map((doc) => {
                    const attached = myDocuments.find((d) => d.label === doc.name);
                    return (
                      <li key={doc.name} className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="text-navy min-w-[10rem]">
                          {doc.name}
                          {doc.required && requiredMark}
                        </span>
                        {attached && (
                          <>
                            <a href={attached.url} target="_blank" rel="noreferrer" className="font-mono text-xs text-blue underline">
                              {attached.file_name}
                            </a>
                            <button type="button" onClick={() => removeDocument.mutate(attached.id)} className="text-xs text-red underline">
                              {t("response.remove")}
                            </button>
                          </>
                        )}
                        <label className="text-xs text-blue underline cursor-pointer">
                          {attached ? t("response.replace") : t("response.upload")}
                          <input
                            type="file"
                            aria-label={`${t("response.upload")} ${doc.name}`}
                            className="sr-only"
                            disabled={uploadMutation.isPending}
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) uploadMutation.mutate({ label: doc.name, file });
                              e.target.value = "";
                            }}
                          />
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </fieldset>
            )}
            {rules.declarations.length > 0 && (
              <fieldset>
                <legend className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("response.declarations")}</legend>
                <div className="grid gap-1.5">
                  {rules.declarations.map((text) => (
                    <label key={text} className="flex items-start gap-2 text-sm text-navy">
                      <input
                        type="checkbox"
                        className="mt-1"
                        required
                        checked={accepted.includes(text)}
                        onChange={(e) => setAccepted((a) => (e.target.checked ? [...a, text] : a.filter((x) => x !== text)))}
                      />
                      {text}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={submitMutation.isPending}
                className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
              >
                {existingOffer ? t("service_provider.offer.updateOffer") : t("service_provider.offer.submitOffer")}
              </button>
              {existingOffer && existingOffer.status !== "withdrawn" && (
                <button
                  type="button"
                  onClick={() => withdrawMutation.mutate()}
                  disabled={withdrawMutation.isPending}
                  className="text-xs text-red underline disabled:opacity-60"
                >
                  {withdrawMutation.isPending ? t("service_provider.offer.withdrawing") : t("service_provider.offer.withdraw")}
                </button>
              )}
            </div>
          </form>

          <div className="bg-white border border-border rounded px-4.5 py-4">
            <h3 className="font-mono text-[13px] uppercase tracking-wide text-navy mb-2">{t("service_provider.offer.tipsHeading")}</h3>
            <ul className="text-[13px] text-steel leading-[1.7] list-disc pl-[18px]">
              <li>{t("service_provider.offer.tip1")}</li>
              <li>{t("service_provider.offer.tip2")}</li>
              <li>{t("service_provider.offer.tip3")}</li>
            </ul>
          </div>
        </div>
      </fieldset>
    </>
  );
}
