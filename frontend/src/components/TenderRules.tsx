import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ProjectDetail, TenderType } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { localInputToUtcIso, toLocalInputValue } from "@/lib/dates";
import { formatDeadline } from "@/lib/format";

// Stage 3.10: the rules of participation, kept apart from the requirement
// itself. The offer deadline stays with the dates (Stage 3.7) and the
// declarations with the response requirements (3.8); this sets the rest.
// The server enforces each rule from the same fields (services/tender_rules).

let nextKey = 1;

export function TenderRulesEditor({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const rules = project.tender_rules;
  const initial = () => ({
    tender_type: project.tender_type,
    questions_allowed: rules.questions_allowed,
    questions_deadline: rules.questions_deadline ? toLocalInputValue(rules.questions_deadline) : "",
    validity: rules.commercial_conditions.offer_validity_days ? String(rules.commercial_conditions.offer_validity_days) : "",
    stages: rules.commercial_conditions.payment_stages.map((s) => ({ key: nextKey++, milestone: s.milestone, percent: String(Number(s.percent)) })),
    retention_percent: rules.commercial_conditions.retention_percent ? String(Number(rules.commercial_conditions.retention_percent)) : "",
    retention_months: rules.commercial_conditions.retention_months ? String(rules.commercial_conditions.retention_months) : "",
    warranty: rules.commercial_conditions.warranty_months ? String(rules.commercial_conditions.warranty_months) : "",
    commercial_terms: rules.commercial_terms ?? "",
    bidder_instructions: rules.bidder_instructions ?? "",
  });
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setValues(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.tender_type, JSON.stringify(rules)]);

  const strip = (v: typeof values) => ({ ...v, stages: v.stages.map(({ milestone, percent }) => ({ milestone, percent })) });
  const dirty = JSON.stringify(strip(values)) !== JSON.stringify(strip(initial()));
  const stagesTotal = values.stages.reduce((sum, s) => sum + (Number(s.percent) || 0), 0);
  const num = (v: string) => (v.trim() ? Number(v) : null);
  const set = (patch: Partial<typeof values>) => {
    setSaved(false);
    setValues((v) => ({ ...v, ...patch }));
  };

  const save = useMutation({
    mutationFn: () =>
      apiFetch<ProjectDetail>(`/projects/${project.id}/tender-rules`, {
        method: "PUT",
        body: {
          tender_type: values.tender_type,
          questions_allowed: values.questions_allowed,
          questions_deadline: values.questions_allowed && values.questions_deadline ? localInputToUtcIso(values.questions_deadline) : null,
          commercial_conditions: {
            offer_validity_days: num(values.validity),
            payment_stages: values.stages.filter((s) => s.milestone.trim() || s.percent).map((s) => ({ milestone: s.milestone.trim(), percent: s.percent })),
            retention_percent: values.retention_percent || null,
            retention_months: num(values.retention_months),
            warranty_months: num(values.warranty),
          },
          commercial_terms: values.commercial_terms || null,
          bidder_instructions: values.bidder_instructions || null,
        },
      }),
    onSuccess: (data) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(["project", project.id], data);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("tenderRules.saveError")),
  });

  const legend = "font-display text-sm font-semibold text-navy";
  const hint = "text-xs text-steel-light";
  const field = "w-full border border-border rounded px-3 py-2 text-sm";
  return (
    <section className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-2xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("tenderRules.heading")}</h2>
      <p className={`${hint} mb-3`}>{t("tenderRules.hint")}</p>
      <ErrorBanner message={error} />
      <form
        className="grid gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div>
          <div className={legend}>{t("tenderRules.offersClose")}</div>
          <p className="text-sm text-navy font-mono">{formatDeadline(project.bid_deadline)}</p>
          <p className={hint}>{t("tenderRules.offersCloseHint")}</p>
        </div>

        <fieldset>
          <legend className={`${legend} mb-1`}>{t("tenderRules.visibility")}</legend>
          {(["owner_visible", "sealed"] as TenderType[]).map((type) => (
            <label key={type} className="flex items-center gap-2 text-sm text-navy">
              <input
                type="radio"
                name="tender_type"
                checked={values.tender_type === type}
                disabled={project.tender_type_locked}
                onChange={() => set({ tender_type: type })}
              />
              {t(type === "sealed" ? "tenderRules.sealed" : "tenderRules.ownerVisible")}
            </label>
          ))}
        </fieldset>

        <fieldset className="border-t border-border pt-4">
          <legend className={`${legend} pt-4 mb-1`}>{t("tenderRules.questions")}</legend>
          <label className="flex items-center gap-2 text-sm text-navy mb-2">
            <input type="checkbox" checked={values.questions_allowed} onChange={(e) => set({ questions_allowed: e.target.checked })} />
            {t("tenderRules.questionsAllowed")}
          </label>
          {values.questions_allowed && (
            <div>
              <label htmlFor="questions-deadline" className="block text-xs text-steel mb-1">{t("tenderRules.questionsUntil")}</label>
              <input
                id="questions-deadline"
                type="datetime-local"
                value={values.questions_deadline}
                max={toLocalInputValue(project.bid_deadline)}
                onChange={(e) => set({ questions_deadline: e.target.value })}
                className="border border-border rounded px-3 py-2 text-sm"
              />
              <p className={`${hint} mt-1`}>{t("tenderRules.questionsUntilHint")}</p>
            </div>
          )}
        </fieldset>

        <fieldset className="border-t border-border pt-4 grid gap-3">
          <div className={`${legend} pt-4`}>{t("tenderRules.commercialTerms")}</div>
          <p className={`${hint} -mt-2`}>{t("tenderRules.commercialTermsHint")}</p>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="text-xs text-steel">
              {t("tenderRules.offerValidity")}
              <input type="number" min={1} max={365} value={values.validity} onChange={(e) => set({ validity: e.target.value })} className={`${field} mt-1`} />
            </label>
            <label className="text-xs text-steel">
              {t("tenderRules.warranty")}
              <input type="number" min={1} max={240} value={values.warranty} onChange={(e) => set({ warranty: e.target.value })} className={`${field} mt-1`} />
            </label>
          </div>
          <div>
            <div className="text-xs text-steel">{t("tenderRules.paymentStages")}</div>
            <p className={`${hint} mb-1`}>{t("tenderRules.paymentStagesHint")}</p>
            <div className="grid gap-1.5">
              {values.stages.map((s, i) => (
                <div key={s.key} className="flex items-center gap-2">
                  <input
                    aria-label={t("tenderRules.milestone")}
                    placeholder={t("tenderRules.milestone")}
                    value={s.milestone}
                    maxLength={200}
                    onChange={(e) => set({ stages: values.stages.map((x, j) => (j === i ? { ...x, milestone: e.target.value } : x)) })}
                    className={`${field} flex-1`}
                  />
                  <input
                    aria-label={`${t("tenderRules.percent")} ${i + 1}`}
                    type="number"
                    min={0.01}
                    max={100}
                    step="0.01"
                    value={s.percent}
                    onChange={(e) => set({ stages: values.stages.map((x, j) => (j === i ? { ...x, percent: e.target.value } : x)) })}
                    className="w-20 border border-border rounded px-2 py-2 text-sm"
                  />
                  <span className="text-xs text-steel">%</span>
                  <button type="button" onClick={() => set({ stages: values.stages.filter((_, j) => j !== i) })} className="text-xs text-red underline">
                    {t("tenderRules.remove")}
                  </button>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-3 mt-1">
              {values.stages.length < 10 && (
                <button type="button" onClick={() => set({ stages: [...values.stages, { key: nextKey++, milestone: "", percent: "" }] })} className="text-xs text-blue underline">
                  + {t("tenderRules.addStage")}
                </button>
              )}
              {values.stages.length > 0 && (
                <span className={`text-xs font-mono ${stagesTotal === 100 ? "text-green" : "text-amber-dark"}`}>
                  {t("tenderRules.stagesTotal").replace("{total}", String(Math.round(stagesTotal * 100) / 100))}
                </span>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <span className="text-xs text-steel pb-2.5">{t("tenderRules.retention")}</span>
            <label className="text-xs text-steel">
              {t("tenderRules.retentionPercent")}
              <input type="number" min={0.01} max={100} step="0.01" value={values.retention_percent} onChange={(e) => set({ retention_percent: e.target.value })} className="block w-24 border border-border rounded px-2 py-2 text-sm mt-1" />
            </label>
            <label className="text-xs text-steel">
              {t("tenderRules.retentionMonths")}
              <input type="number" min={1} max={120} value={values.retention_months} onChange={(e) => set({ retention_months: e.target.value })} className="block w-24 border border-border rounded px-2 py-2 text-sm mt-1" />
            </label>
          </div>
          <div>
            <label htmlFor="commercial-terms" className="text-xs text-steel">{t("tenderRules.otherConditions")}</label>
            <textarea
              id="commercial-terms"
              rows={3}
              maxLength={5000}
              value={values.commercial_terms}
              onChange={(e) => set({ commercial_terms: e.target.value })}
              className={`${field} resize-y mt-1`}
            />
          </div>
          <div>
            <label htmlFor="bidder-instructions" className={`${legend} block`}>{t("tenderRules.instructions")}</label>
            <p className={`${hint} mb-1`}>{t("tenderRules.instructionsHint")}</p>
            <textarea
              id="bidder-instructions"
              rows={3}
              maxLength={5000}
              value={values.bidder_instructions}
              onChange={(e) => set({ bidder_instructions: e.target.value })}
              className={`${field} resize-y`}
            />
          </div>
        </fieldset>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={save.isPending || !dirty} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5 w-fit">
            {t("tenderRules.save")}
          </button>
          {saved && !dirty && <span className="text-xs text-green">{t("tenderRules.saved")}</span>}
        </div>
      </form>
    </section>
  );
}

// What a provider is told before responding. Every line comes from the same
// fields the server enforces.
export function ParticipationRules({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const rules = project.tender_rules;
  const declarations = project.response_requirements.declarations.length;
  const questions = !rules.questions_allowed
    ? t("tenderRules.pNoQuestions")
    : rules.questions_open && rules.questions_close_at
      ? t("tenderRules.pQuestionsUntil").replace("{date}", formatDeadline(rules.questions_close_at))
      : t("tenderRules.pQuestionsClosed");
  return (
    <section className="mb-6 bg-white border border-border rounded px-4 py-3">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1.5">{t("tenderRules.providerHeading")}</h3>
      <ul className="text-sm text-navy list-disc ps-5 leading-[1.8]">
        <li>{t("tenderRules.pOffersClose").replace("{date}", formatDeadline(project.bid_deadline))}</li>
        <li>{t("tenderRules.pRevise")}</li>
        <li>{t(project.tender_type === "sealed" ? "tenderRules.pSealed" : "tenderRules.pOwnerVisible")}</li>
        <li>{questions}</li>
        {declarations > 0 && <li>{t("tenderRules.pDeclarations").replace("{count}", String(declarations))}</li>}
      </ul>
      <CommercialConditionsView rules={rules} />
      {rules.bidder_instructions && (
        <div className="mt-3">
          <h4 className="font-mono text-[10.5px] uppercase tracking-wide text-steel mb-0.5">{t("tenderRules.pInstructions")}</h4>
          <p className="text-sm text-navy whitespace-pre-wrap break-words">{rules.bidder_instructions}</p>
        </div>
      )}
    </section>
  );
}

// The commercial conditions as short, readable lines.
function CommercialConditionsView({ rules }: { rules: ProjectDetail["tender_rules"] }) {
  const { t } = useI18n();
  const c = rules.commercial_conditions;
  const pct = (v: string) => String(Number(v));
  const lines = [
    ...(c.offer_validity_days ? [t("tenderRules.pValidity").replace("{days}", String(c.offer_validity_days))] : []),
    ...(c.payment_stages.length ? [`${t("tenderRules.pPayment")} ${c.payment_stages.map((s) => `${pct(s.percent)}% ${s.milestone}`).join(" · ")}`] : []),
    ...(c.retention_percent && c.retention_months
      ? [t("tenderRules.pRetention").replace("{percent}", pct(c.retention_percent)).replace("{months}", String(c.retention_months))]
      : []),
    ...(c.warranty_months ? [t("tenderRules.pWarranty").replace("{months}", String(c.warranty_months))] : []),
  ];
  if (!lines.length && !rules.commercial_terms) return null;
  return (
    <div className="mt-3">
      <h4 className="font-mono text-[10.5px] uppercase tracking-wide text-steel mb-0.5">{t("tenderRules.pCommercial")}</h4>
      {lines.length > 0 && (
        <ul className="text-sm text-navy list-disc ps-5 leading-[1.8]">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {rules.commercial_terms && (
        <div className="mt-1.5">
          <div className="text-xs text-steel">{t("tenderRules.pOther")}</div>
          <p className="text-sm text-navy whitespace-pre-wrap break-words">{rules.commercial_terms}</p>
        </div>
      )}
    </div>
  );
}
