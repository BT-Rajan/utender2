import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ProjectDetail } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { localInputToUtcIso, toLocalInputValue } from "@/lib/dates";

// Stage 3.7: the two kinds of date on a draft requirement, kept visibly
// apart -- the offer deadline (bid_deadline, the one the server enforces)
// and the expected timing of the work itself.
export function DraftDates({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const initial = () => ({
    deadline: toLocalInputValue(project.bid_deadline),
    start: project.expected_start_date ?? "",
    completion: project.expected_completion_date ?? "",
    duration: project.expected_duration_days ? String(project.expected_duration_days) : "",
  });
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setValues(initial());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.bid_deadline, project.expected_start_date, project.expected_completion_date, project.expected_duration_days]);

  const dirty = JSON.stringify(values) !== JSON.stringify(initial());
  const set = (patch: Partial<typeof values>) => {
    setSaved(false);
    setValues((v) => ({ ...v, ...patch }));
  };

  const save = useMutation({
    mutationFn: () =>
      apiFetch<ProjectDetail>(`/projects/${project.id}`, {
        method: "PATCH",
        body: {
          bid_deadline: localInputToUtcIso(values.deadline),
          expected_start_date: values.start || null,
          expected_completion_date: values.completion || null,
          expected_duration_days: values.duration ? Number(values.duration) : null,
        },
      }),
    onSuccess: (data) => {
      setError(null);
      setSaved(true);
      queryClient.setQueryData(["project", project.id], data);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("dates.saveError")),
  });

  const label = "block text-xs text-steel mb-1";
  const field = "w-full border border-border rounded px-3 py-2 text-sm";
  const deadlinePassed = new Date(project.bid_deadline) <= new Date();
  return (
    <section className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-2xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-3">{t("dates.heading")}</h2>
      <ErrorBanner message={error} />
      <form
        className="grid gap-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <fieldset>
          <legend className="font-display text-sm font-semibold text-navy">{t("dates.responseHeading")}</legend>
          <p className="text-xs text-steel-light mb-2">{t("dates.responseHint")}</p>
          <input
            type="datetime-local"
            aria-label={t("dates.responseHeading")}
            value={values.deadline}
            onChange={(e) => set({ deadline: e.target.value })}
            required
            className="border border-border rounded px-3 py-2 text-sm"
          />
          {deadlinePassed && !dirty && <p className="text-xs text-amber-dark mt-1">{t("dates.pastDeadline")}</p>}
        </fieldset>

        <fieldset className="border-t border-border pt-4">
          <legend className="font-display text-sm font-semibold text-navy pt-4">{t("dates.workHeading")}</legend>
          <p className="text-xs text-steel-light mb-2">{t("dates.workHint")}</p>
          <div className="grid sm:grid-cols-[1fr_1fr_auto_8rem] gap-3 items-end">
            <div>
              <label htmlFor="work-start" className={label}>{t("dates.start")}</label>
              <input id="work-start" type="date" value={values.start} onChange={(e) => set({ start: e.target.value })} className={field} />
            </div>
            <div>
              <label htmlFor="work-completion" className={label}>{t("dates.completion")}</label>
              <input
                id="work-completion"
                type="date"
                value={values.completion}
                min={values.start || undefined}
                onChange={(e) => set({ completion: e.target.value, duration: e.target.value ? "" : values.duration })}
                className={field}
              />
            </div>
            <span className="text-xs text-steel pb-2.5">{t("dates.durationOr")}</span>
            <div>
              <label htmlFor="work-duration" className={label}>{t("dates.duration")}</label>
              <input
                id="work-duration"
                type="number"
                min={1}
                max={3650}
                value={values.duration}
                onChange={(e) => set({ duration: e.target.value, completion: e.target.value ? "" : values.completion })}
                className={field}
              />
            </div>
          </div>
        </fieldset>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={save.isPending || !dirty} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5 w-fit">
            {t("dates.save")}
          </button>
          {saved && !dirty && <span className="text-xs text-green">{t("dates.saved")}</span>}
        </div>
      </form>
    </section>
  );
}
