import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { Offer, OfferDocument, OfferReadiness, ProjectDetail } from "@/api/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { ErrorBanner } from "@/components/ErrorBanner";
import { OfferPreview, SECTION_ANCHORS } from "@/components/OfferPreview";
import { OutdatedOfferNotice } from "@/components/PostPublication";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";
import { money, normalizeAmountInput } from "@/lib/money";

// The provider's offer form. Shared by the provider's page and the owner's
// preview (Stage 3.13), where it is shown read-only: the owner sees exactly
// the fields a provider will fill in -- the item rate table, the required
// fields, the requested documents, the declarations -- and nothing is sent.
export function OfferForm({
  project,
  existingOffer,
  draft = null,
  preview = false,
}: {
  project: ProjectDetail;
  existingOffer: Offer | null;
  // Stage 5.2/5.3: the provider's unsubmitted draft, when there is one.
  draft?: Offer | null;
  preview?: boolean;
}) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [amount, setAmount] = useState("");
  const [timeline, setTimeline] = useState("");
  const [message, setMessage] = useState("");
  const [assumptions, setAssumptions] = useState("");
  const [rates, setRates] = useState<Record<string, string>>({});
  const [accepted, setAccepted] = useState<string[]>([]);
  const [savedNotice, setSavedNotice] = useState(false);
  // Stage 5.5: the execution commitment, in the requirement's terms.
  const [startDate, setStartDate] = useState("");
  const [completionDate, setCompletionDate] = useState("");
  const [durationDays, setDurationDays] = useState("");
  // Stage 5.10: what was last saved, to tell typed-but-unsaved changes apart
  // and warn before they're lost by leaving or refreshing the page.
  const [savedSnapshot, setSavedSnapshot] = useState<string | null>(null);
  const currentSnapshot = snapshotOf({ amount, rates, message, timeline, assumptions, accepted, startDate, completionDate, durationDays });
  const unsaved = !!draft && !existingOffer && !preview && savedSnapshot !== null && currentSnapshot !== savedSnapshot;
  useEffect(() => {
    if (!unsaved) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);
  // Stage 5.9: preview the saved draft; the form stays mounted (hidden) so nothing typed is lost.
  const [previewing, setPreviewing] = useState(false);
  const backToEdit = (anchor?: string | null) => {
    setPreviewing(false);
    if (anchor) setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "center" }), 0);
  };

  // Stage 5.3-5.10: everything saved on the draft, when returning to it.
  useEffect(() => {
    if (draft && !existingOffer) {
      const saved = {
        amount: draft.amount === null ? "" : String(Number(draft.amount)),
        rates: Object.fromEntries((draft.item_prices ?? []).map((l) => [l.item_id, String(Number(l.rate))])),
        message: draft.message ?? "",
        timeline: draft.timeline_estimate ?? "",
        assumptions: draft.assumptions ?? "",
        accepted: draft.declarations_accepted ?? [],
        startDate: draft.proposed_start_date ?? "",
        completionDate: draft.proposed_completion_date ?? "",
        durationDays: draft.proposed_duration_days == null ? "" : String(draft.proposed_duration_days),
      };
      setAmount(saved.amount);
      setRates(saved.rates);
      setMessage(saved.message);
      setTimeline(saved.timeline);
      setAssumptions(saved.assumptions);
      setAccepted(saved.accepted);
      setStartDate(saved.startDate);
      setCompletionDate(saved.completionDate);
      setDurationDays(saved.durationDays);
      setSavedSnapshot(snapshotOf(saved));
    }
    // Only when a different draft (or a newer save of it) arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.id, draft?.draft_version]);

  useEffect(() => {
    if (existingOffer) {
      setAmount(existingOffer.amount === null ? "" : String(Number(existingOffer.amount)));
      setTimeline(existingOffer.timeline_estimate ?? "");
      setStartDate(existingOffer.proposed_start_date ?? "");
      setCompletionDate(existingOffer.proposed_completion_date ?? "");
      setDurationDays(existingOffer.proposed_duration_days == null ? "" : String(existingOffer.proposed_duration_days));
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
    // Stage 5.6: links last an hour; fetch fresh ones before they lapse.
    refetchInterval: 20 * 60 * 1000,
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
  const clean = normalizeAmountInput;
  // Shown as a guide only; the server computes the authoritative total.
  const lineTotal = (rate: string, quantity: string | null) => {
    if (!clean(rate)) return null;
    const value = Number(clean(rate)) * (quantity === null ? 1 : Number(quantity));
    return Math.round(value * 1000) / 1000;
  };
  const itemTotal = project.items.reduce((sum, item) => sum + (lineTotal(rates[item.id] ?? "", item.quantity) ?? 0), 0) ?? 0;

  const submitMutation = useMutation({
    // Stage 5.13: a revision sends the revision it was made from (If-Match),
    // so a newer one from another tab or a colleague is never overwritten,
    // and carries the whole offer, timing included.
    mutationFn: () =>
      apiFetch(`/projects/${project.id}/offers`, {
        method: "POST",
        headers: existingOffer ? { "If-Match": String(existingOffer.revision) } : undefined,
        body: {
          amount: perItem ? null : clean(amount),
          item_prices: perItem ? project.items.map((item) => ({ item_id: item.id, rate: clean(rates[item.id] ?? "") })) : null,
          timeline_estimate: timeline || null,
          message: message || null,
          assumptions: assumptions || null,
          accepted_declarations: accepted,
          proposed_start_date: startDate || null,
          proposed_completion_date: completionDate || null,
          proposed_duration_days: durationDays ? Number(durationDays) : null,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["my-offer", project.id] });
      queryClient.invalidateQueries({ queryKey: ["my-offer-history", project.id] });
      queryClient.invalidateQueries({ queryKey: ["service-provider-feed"] });
    },
    // Stage 5.15: a refusal (deadline passed, closed, suspended...) shows the
    // requirement as the server now has it. The offer itself isn't re-read
    // here, so a stale-page refusal never overwrites what was typed.
    onError: () => queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
  });

  // Stage 5.3/5.4: save the price, then the technical response, on the
  // draft -- nothing is submitted. The server prices it on the requirement's
  // basis and computes every total; If-Match makes a save from a stale tab
  // fail instead of overwriting (each save moves the draft's version on).
  // Stage 5.10: save the whole form on the draft in one step -- nothing is
  // submitted. The server checks every part before writing any of it (so a
  // failure leaves the saved draft as it was), prices it on the requirement's
  // basis, and refuses a save from a stale page (If-Match) instead of
  // overwriting newer work.
  const saveDraftMutation = useMutation({
    mutationFn: (_snapshot: string) =>
      apiFetch<Offer>(`/projects/${project.id}/offers/draft`, {
        method: "PUT",
        headers: draft ? { "If-Match": String(draft.draft_version ?? 0) } : undefined,
        body: {
          amount: perItem || !clean(amount) ? null : clean(amount),
          item_prices: perItem
            ? project.items.filter((item) => clean(rates[item.id] ?? "")).map((item) => ({ item_id: item.id, rate: clean(rates[item.id] ?? "") }))
            : null,
          message: message || null,
          assumptions: assumptions || null,
          accepted_declarations: accepted,
          proposed_start_date: startDate || null,
          proposed_completion_date: completionDate || null,
          proposed_duration_days: durationDays ? Number(durationDays) : null,
          timeline_estimate: timeline || null,
        },
      }),
    onSuccess: (saved, snapshot) => {
      setError(null);
      setSavedNotice(true);
      setSavedSnapshot(snapshot);
      queryClient.setQueryData(["my-offer", project.id], saved);
      queryClient.invalidateQueries({ queryKey: ["offer-check", project.id] });
      queryClient.invalidateQueries({ queryKey: ["offer-preview", project.id] });
    },
    onError: (err) => {
      setSavedNotice(false);
      setError(err instanceof ApiError ? err.detail : t("response.saveDraftError"));
    },
  });

  // Stage 5.14: withdrawing is decided by the server (open, before the
  // deadline, the provider's own offer); the page asks first and then shows
  // the server's answer -- a refusal refreshes to the current state.
  const withdrawMutation = useMutation({
    mutationFn: () => apiFetch<Offer>(`/projects/${project.id}/offers/withdraw`, { method: "POST" }),
    onSuccess: (withdrawn) => {
      setError(null);
      queryClient.setQueryData(["my-offer", project.id], withdrawn);
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["my-offer", project.id] });
      queryClient.invalidateQueries({ queryKey: ["my-offer-history", project.id] });
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("service_provider.offer.withdrawError")),
  });

  // Stage 5.11: a draft is submitted as stored -- the form is saved first
  // (one step, 5.10), then that saved version (If-Match) is submitted, so
  // what goes to the owner is exactly what the preview shows. The server
  // re-checks everything at that moment. A submitted offer is revised
  // through the existing route.
  const submitDraftMutation = useMutation({
    mutationFn: async () => {
      const saved = await saveDraftMutation.mutateAsync(currentSnapshot);
      return apiFetch<Offer>(`/projects/${project.id}/offers/draft/submit`, {
        method: "POST",
        headers: { "If-Match": String(saved.draft_version ?? 0) },
      });
    },
    onSuccess: (submitted) => {
      setSavedNotice(false);
      queryClient.setQueryData(["my-offer", project.id], submitted);
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
      queryClient.invalidateQueries({ queryKey: ["service-provider-feed"] });
      queryClient.invalidateQueries({ queryKey: ["service-provider-preparing"] });
    },
    // A refusal (incomplete, closed, changed...) leaves the draft as saved; the checks say why.
    // Stage 5.15: and the page re-reads the server's state -- e.g. "already
    // submitted" by another tab or a colleague shows that submitted offer.
    onError: () => {
      queryClient.invalidateQueries({ queryKey: ["my-offer", project.id] });
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["offer-check", project.id] }),
  });

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const isDraft = !!draft && !existingOffer;
    if (isDraft) {
      const ok = await confirm({
        title: t("submitOffer.confirmTitle"),
        body: t("submitOffer.confirmBody"),
        confirmLabel: t("service_provider.offer.submitOffer"),
      });
      if (!ok) return;
    } else if (existingOffer) {
      // Stage 5.13: revising a submitted (or withdrawn) offer replaces the current version.
      const ok = await confirm({
        title: t("submitOffer.reviseTitle"),
        body: t("submitOffer.reviseBody"),
        confirmLabel: t("service_provider.offer.updateOffer"),
      });
      if (!ok) return;
    }
    try {
      await (isDraft ? submitDraftMutation.mutateAsync() : submitMutation.mutateAsync());
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
      {previewing && draft && <OfferPreview projectId={project.id} onEdit={backToEdit} />}
      <div className={previewing ? "hidden" : undefined}>
      {draft && !existingOffer && !preview && <ReadinessPanel projectId={project.id} onGoTo={backToEdit} />}
      {existingOffer && !preview && <OutdatedOfferNotice project={project} offer={existingOffer} />}
      <fieldset disabled={preview} className={preview ? "opacity-80" : undefined}>
        <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-6 items-start">
          <form onSubmit={handleSubmit} className="grid gap-[18px]">
            {perItem ? (
              <div className="overflow-x-auto" id="offer-section-price">
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
              <div id="offer-section-price">
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
                required={rules.completion_period === "required" && !completionDate && !durationDays}
                placeholder={t("service_provider.offer.timelinePlaceholder")}
                className="w-full border border-border rounded px-3 py-2.5 text-sm"
              />
            </div>
            {/* Stage 5.5: when the provider commits to start and finish, beside what the owner expects (Stage 3.7). */}
            <fieldset className="grid gap-2" data-testid="timing-commitment" id="offer-section-timing">
              <legend className="font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("timing.heading")}</legend>
              {(project.expected_start_date || project.expected_completion_date || project.expected_duration_days) && (
                <p className="text-xs text-steel" data-testid="owner-timing">
                  {t("timing.ownerExpects")}
                  {project.expected_start_date && ` ${t("timing.start")} ${fullDate(project.expected_start_date, language, false)}`}
                  {project.expected_completion_date && ` · ${t("timing.completion")} ${fullDate(project.expected_completion_date, language, false)}`}
                  {project.expected_duration_days && ` · ${t("timing.duration")} ${project.expected_duration_days} ${t("timing.days")}`}
                </p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <label className="text-xs text-steel">
                  {t("timing.start")}
                  <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="mt-1 w-full border border-border rounded px-3 py-2 text-sm" />
                </label>
                <label className="text-xs text-steel">
                  {t("timing.completion")}
                  <input type="date" value={completionDate} min={startDate || undefined} disabled={!!durationDays} onChange={(e) => setCompletionDate(e.target.value)} className="mt-1 w-full border border-border rounded px-3 py-2 text-sm disabled:opacity-50" />
                </label>
                <label className="text-xs text-steel">
                  {t("timing.durationDays")}
                  <input type="number" min={1} max={3650} step={1} value={durationDays} disabled={!!completionDate} onChange={(e) => setDurationDays(e.target.value.replace(/[^0-9]/g, ""))} className="mt-1 w-full border border-border rounded px-3 py-2 text-sm disabled:opacity-50" />
                </label>
              </div>
              <p className="text-xs text-steel-light">{t("timing.hint")}</p>
              {(draft ?? existingOffer)?.timing_conflicts?.map((code) => (
                <p key={code} className="text-xs text-amber-dark" data-testid="timing-conflict">⚠ {t(`timing.conflict_${code}`)}</p>
              ))}
            </fieldset>
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
                maxLength={10000}
              />
              {/* Stage 5.4: answer this requirement's own specifications and instructions, shown above. */}
              {(project.items.some((item) => item.specification) || project.tender_rules.bidder_instructions) && (
                <p className="text-xs text-steel mt-1" data-testid="approach-guide">{t("response.approachGuide")}</p>
              )}
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
              {/* Stage 5.7: conditions on this offer -- not questions about the requirement (Q&A above). */}
              <p className="text-xs text-steel mt-1" data-testid="assumptions-guide">{t("response.assumptionsGuide")}</p>
            </div>
            {rules.documents.length > 0 && (
              <fieldset id="offer-section-documents">
                <legend className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("response.attachments")}</legend>
                {existingOffer && !preview && <p className="text-xs text-steel mb-1.5" data-testid="docs-on-update">{t("submitOffer.docsOnUpdate")}</p>}
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
              <fieldset id="offer-section-declarations">
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
                disabled={submitMutation.isPending || submitDraftMutation.isPending}
                className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
              >
                {existingOffer?.status === "withdrawn"
                  ? t("submitOffer.resubmit")
                  : existingOffer
                    ? t("service_provider.offer.updateOffer")
                    : t("service_provider.offer.submitOffer")}
              </button>
              {draft && !existingOffer && !preview && (
                <button
                  type="button"
                  onClick={() => saveDraftMutation.mutate(currentSnapshot)}
                  disabled={saveDraftMutation.isPending}
                  className="border border-navy text-navy font-semibold text-sm rounded px-4 py-2.5 disabled:opacity-60"
                  data-testid="save-draft"
                >
                  {t("response.saveDraft")}
                </button>
              )}
              {draft && !existingOffer && !preview && (
                <button type="button" onClick={() => setPreviewing(true)} className="text-sm text-blue underline" data-testid="preview-offer">
                  {t("offerPreview.open")}
                </button>
              )}
              {unsaved && !saveDraftMutation.isPending && (
                <span className="text-xs text-amber-dark" data-testid="unsaved">{t("response.unsaved")}</span>
              )}
              {savedNotice && !unsaved && !saveDraftMutation.isPending && (
                <span className="text-xs text-green" data-testid="draft-saved">{t("response.draftSaved")}</span>
              )}
              {existingOffer && existingOffer.status !== "withdrawn" && (
                <button
                  type="button"
                  onClick={async () => {
                    const ok = await confirm({
                      title: t("submitOffer.withdrawTitle"),
                      body: t("submitOffer.withdrawBody"),
                      confirmLabel: t("service_provider.offer.withdraw"),
                      tone: "danger",
                    });
                    if (ok) withdrawMutation.mutate();
                  }}
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
      </div>
    </>
  );
}

// Stage 5.8: the server's quality gate for the saved draft -- ready to
// submit, or everything still to do, by part of the offer. It checks the
// saved draft (save first), and decides nothing: submitting checks again.
function ReadinessPanel({ projectId, onGoTo }: { projectId: string; onGoTo: (anchor?: string | null) => void }) {
  const { t } = useI18n();
  const { data: check, refetch, isFetching } = useQuery({
    queryKey: ["offer-check", projectId],
    queryFn: () => apiFetch<OfferReadiness>(`/projects/${projectId}/offers/draft/check`),
  });
  if (!check) return null;
  return (
    <div
      className={`rounded px-4 py-3 mb-4 text-sm border ${check.ready ? "border-green bg-green/5" : "border-amber-dark/40 bg-amber/10"}`}
      data-testid="offer-readiness"
    >
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <strong className="font-display text-navy">{check.ready ? t("readiness.ready") : t("readiness.notReady")}</strong>
        <button type="button" onClick={() => refetch()} disabled={isFetching} className="text-xs text-blue underline disabled:opacity-60">
          {t("readiness.recheck")}
        </button>
      </div>
      {!check.ready && (
        <ul className="mt-2 grid gap-1">
          {check.issues.map((issue, i) => (
            <li key={i} className="text-steel">
              <span className="font-mono text-[10px] uppercase text-navy me-2">{t(`readiness.section_${issue.section}`)}</span>
              {issue.message}
              {SECTION_ANCHORS[issue.section] && (
                <button type="button" onClick={() => onGoTo(SECTION_ANCHORS[issue.section])} className="ms-2 text-xs text-blue underline">
                  {t("offerPreview.fix")}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-steel-light mt-2">{t("readiness.savedOnly")}</p>
    </div>
  );
}

// Stage 5.10: a comparable picture of the form's saved fields.
function snapshotOf(v: {
  amount: string;
  rates: Record<string, string>;
  message: string;
  timeline: string;
  assumptions: string;
  accepted: string[];
  startDate: string;
  completionDate: string;
  durationDays: string;
}): string {
  const rates = Object.fromEntries(Object.entries(v.rates).filter(([, r]) => r !== "").sort(([a], [b]) => a.localeCompare(b)));
  return JSON.stringify({ ...v, rates, accepted: [...v.accepted].sort() });
}
