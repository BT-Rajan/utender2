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

export function TenderRulesEditor({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const rules = project.tender_rules;
  const initial = () => ({
    tender_type: project.tender_type,
    questions_allowed: rules.questions_allowed,
    questions_deadline: rules.questions_deadline ? toLocalInputValue(rules.questions_deadline) : "",
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

  const dirty = JSON.stringify(values) !== JSON.stringify(initial());
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
          <div>
            <label htmlFor="commercial-terms" className={`${legend} block pt-4`}>{t("tenderRules.commercialTerms")}</label>
            <p className={`${hint} mb-1`}>{t("tenderRules.commercialTermsHint")}</p>
            <textarea
              id="commercial-terms"
              rows={4}
              maxLength={5000}
              value={values.commercial_terms}
              onChange={(e) => set({ commercial_terms: e.target.value })}
              className={`${field} resize-y`}
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
      {rules.commercial_terms && (
        <div className="mt-3">
          <h4 className="font-mono text-[10.5px] uppercase tracking-wide text-steel mb-0.5">{t("tenderRules.pCommercial")}</h4>
          <p className="text-sm text-navy whitespace-pre-wrap break-words">{rules.commercial_terms}</p>
        </div>
      )}
      {rules.bidder_instructions && (
        <div className="mt-3">
          <h4 className="font-mono text-[10.5px] uppercase tracking-wide text-steel mb-0.5">{t("tenderRules.pInstructions")}</h4>
          <p className="text-sm text-navy whitespace-pre-wrap break-words">{rules.bidder_instructions}</p>
        </div>
      )}
    </section>
  );
}
