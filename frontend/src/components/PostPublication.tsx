import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError, draftVersion } from "@/api/client";
import type { Offer, ProjectAmendment, ProjectDetail, RequirementVersion } from "@/api/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { localInputToUtcIso, toLocalInputValue } from "@/lib/dates";
import { formatDeadline } from "@/lib/format";

// Stage 3.15: controlling a published requirement. Not a draft: the
// server classifies each change (material or not), records it as a numbered
// amendment, tells the bidders, and flags offers made before a material
// change for their providers to confirm or revise.

function useRefresh(projectId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    queryClient.invalidateQueries({ queryKey: ["amendments", projectId] });
    queryClient.invalidateQueries({ queryKey: ["owner-offers", projectId] });
    queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
  };
}

// Pause / resume, for the owner.
export function PauseControl({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const confirm = useConfirm();
  const refresh = useRefresh(project.id);
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: (action: "pause" | "resume") =>
      apiFetch(`/owner/projects/${project.id}/${action}`, { method: "POST", body: action === "pause" ? { reason } : undefined }),
    onSuccess: () => {
      setError(null);
      setOpen(false);
      setReason("");
      refresh();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("postPub.error")),
  });
  if (project.paused_at) {
    return (
      <div className="border border-amber-dark/40 bg-amber/10 rounded px-4 py-3 mb-6 max-w-2xl text-sm">
        <strong className="font-display text-navy block">{t("postPub.pausedSince").replace("{date}", formatDeadline(project.paused_at))}</strong>
        <p className="text-steel">{project.pause_reason}</p>
        <p className="text-xs text-steel-light mt-1">{t("postPub.pausedDeadline").replace("{date}", formatDeadline(project.bid_deadline))}</p>
        <ErrorBanner message={error} />
        <button
          type="button"
          disabled={act.isPending}
          onClick={() =>
            void confirm({ title: t("postPub.resumeConfirm").replace("{date}", formatDeadline(project.bid_deadline)), confirmLabel: t("postPub.resume") }).then(
              (ok) => ok && act.mutate("resume"),
            )
          }
          className="mt-2 bg-navy hover:bg-navy-deep text-white text-xs font-semibold rounded px-4 py-2"
        >
          {t("postPub.resume")}
        </button>
      </div>
    );
  }
  return (
    <div className="mb-4 max-w-2xl">
      {!open ? (
        <button type="button" onClick={() => setOpen(true)} className="border border-navy text-navy text-xs font-semibold rounded px-4 py-2">
          {t("postPub.pause")}
        </button>
      ) : (
        <form
          className="border border-border rounded px-4 py-3 bg-white grid gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            act.mutate("pause");
          }}
        >
          <label htmlFor="pause-reason" className="text-sm text-navy">{t("postPub.pauseReason")}</label>
          <textarea id="pause-reason" required minLength={3} maxLength={500} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} className="border border-border rounded px-3 py-2 text-sm" />
          <p className="text-xs text-steel-light">{t("postPub.pauseHint")}</p>
          <ErrorBanner message={error} />
          <div className="flex gap-2">
            <button type="submit" disabled={act.isPending} className="bg-navy text-white text-xs font-semibold rounded px-4 py-2">{t("postPub.pause")}</button>
            <button type="button" onClick={() => setOpen(false)} className="border border-border text-steel text-xs font-semibold rounded px-4 py-2">{t("confirm.cancel")}</button>
          </div>
        </form>
      )}
    </div>
  );
}

// Amend a published requirement: the fields that may change after
// publication, with what each kind of change means for providers.
export function AmendPublishedForm({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const refresh = useRefresh(project.id);
  const initial = () => ({
    title: project.title,
    description: project.description ?? "",
    address: project.address ?? "",
    area: project.area ?? "",
    deadline: toLocalInputValue(project.bid_deadline),
    start: project.expected_start_date ?? "",
    completion: project.expected_completion_date ?? "",
    reason: "",
  });
  const [values, setValues] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const set = (patch: Partial<typeof values>) => setValues((v) => ({ ...v, ...patch }));
  const save = useMutation({
    mutationFn: () => {
      const base = initial();
      const body: Record<string, unknown> = { reason: values.reason || null };
      if (values.title !== base.title) body.title = values.title;
      if (values.description !== base.description) body.description = values.description;
      if (values.address !== base.address) body.address = values.address;
      if (values.area !== base.area) body.area = values.area || null;
      if (values.deadline !== base.deadline) body.bid_deadline = localInputToUtcIso(values.deadline);
      if (values.start !== base.start) body.expected_start_date = values.start || null;
      if (values.completion !== base.completion) body.expected_completion_date = values.completion || null;
      return apiFetch<ProjectDetail>(`/projects/${project.id}`, { method: "PATCH", body, headers: draftVersion(project) });
    },
    onSuccess: (data) => {
      setError(null);
      setDone(t((data.material_revision ?? 0) > (project.material_revision ?? 0) ? "postPub.savedMaterial" : "postPub.savedMinor"));
      refresh();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("postPub.error")),
  });
  const field = "w-full border border-border rounded px-3 py-2 text-sm";
  const label = "block text-xs text-steel mb-1";
  return (
    <details className="bg-white border border-border rounded px-5 py-4 mb-6 max-w-2xl">
      <summary className="font-display font-semibold text-navy cursor-pointer">{t("postPub.amendHeading")}</summary>
      <p className="text-xs text-steel-light mt-2 mb-3 whitespace-pre-line">{t("postPub.amendHint")}</p>
      <ErrorBanner message={error} />
      {done && <p className="text-xs text-green mb-2">{done}</p>}
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setDone(null);
          save.mutate();
        }}
      >
        <div><label htmlFor="amend-title" className={label}>{t("draftDetails.title")}</label><input id="amend-title" value={values.title} onChange={(e) => set({ title: e.target.value })} className={field} /></div>
        <div><label htmlFor="amend-description" className={label}>{t("service_provider.offer.scope")}</label><textarea id="amend-description" rows={5} value={values.description} onChange={(e) => set({ description: e.target.value })} className={field} /></div>
        <div className="grid sm:grid-cols-2 gap-3">
          <div><label htmlFor="amend-address" className={label}>{t("postPub.address")}</label><input id="amend-address" value={values.address} onChange={(e) => set({ address: e.target.value })} className={field} /></div>
          <div><label htmlFor="amend-area" className={label}>{t("postPub.area")}</label><input id="amend-area" value={values.area} onChange={(e) => set({ area: e.target.value })} className={field} /></div>
        </div>
        <div className="grid sm:grid-cols-3 gap-3">
          <div><label htmlFor="amend-deadline" className={label}>{t("tenderRules.offersClose")}</label><input id="amend-deadline" type="datetime-local" value={values.deadline} onChange={(e) => set({ deadline: e.target.value })} className={field} /></div>
          <div><label htmlFor="amend-start" className={label}>{t("dates.start")}</label><input id="amend-start" type="date" value={values.start} onChange={(e) => set({ start: e.target.value })} className={field} /></div>
          <div><label htmlFor="amend-completion" className={label}>{t("dates.completion")}</label><input id="amend-completion" type="date" value={values.completion} onChange={(e) => set({ completion: e.target.value })} className={field} /></div>
        </div>
        <div><label htmlFor="amend-reason" className={label}>{t("postPub.reason")}</label><input id="amend-reason" value={values.reason} onChange={(e) => set({ reason: e.target.value })} className={field} /></div>
        <button type="submit" disabled={save.isPending} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5 w-fit">{t("postPub.amendSave")}</button>
      </form>
    </details>
  );
}

// The numbered changes since publication -- for the owner and providers alike.
export function AmendmentsList({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const { data: amendments = [] } = useQuery({
    queryKey: ["amendments", projectId],
    queryFn: () => apiFetch<ProjectAmendment[]>(`/projects/${projectId}/amendments`),
  });
  if (!amendments.length) return null;
  return (
    <section className="mb-6 bg-white border border-border rounded px-4 py-3">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1.5">{t("postPub.changesHeading")}</h3>
      <ul className="text-sm text-navy grid gap-2.5" data-testid="amendments">
        {amendments.map((a) => (
          <li key={a.id}>
            <span className="font-mono text-xs text-steel">#{a.amendment_number} · {formatDeadline(a.created_at)}</span>{" "}
            {a.material && (
              <span className="font-mono text-[10px] uppercase text-amber-dark">
                {t("postPub.material")} · {t("versions.version").replace("{n}", String(a.material_revision ?? ""))}
              </span>
            )}{" "}
            {a.changes ? <ChangeList changes={a.changes} /> : a.summary}
            {a.reason && <span className="block text-xs text-steel">{a.reason}</span>}
            {a.material && !!a.material_revision && (
              <VersionView projectId={projectId} number={a.material_revision - 1} label={t("versions.before").replace("{n}", String(a.material_revision - 1))} />
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

// Stage 3.17: a recorded value, readably.
function showValue(t: (key: string) => string, field: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (field === "bid_deadline") return formatDeadline(String(value));
  if (field === "governorate") return t(`location.${value}`);
  if (typeof value === "boolean") return value ? t("versions.yes") : t("versions.no");
  return String(value);
}

const SHOWN_FIELDS = [
  "title", "address", "governorate", "area", "trade", "description", "bid_deadline",
  "expected_start_date", "expected_completion_date", "expected_duration_days", "documents_required",
];

function ChangeList({ changes }: { changes: NonNullable<ProjectAmendment["changes"]> }) {
  const { t } = useI18n();
  return (
    <ul className="grid gap-1 mt-1 text-[13px]">
      {Object.entries(changes).map(([field, change]) => {
        if (field === "category_id") return null; // shown through the type of work
        if ("added" in change) {
          return (
            <li key={field}>
              {change.added.length > 0 && <span className="block">{t("versions.docsAdded")} {change.added.join(", ")}</span>}
              {change.replaced.length > 0 && <span className="block">{t("versions.docsReplaced")} {change.replaced.join(", ")}</span>}
            </li>
          );
        }
        return (
          <li key={field}>
            <span className="text-steel">{t(`versions.field_${field}`)}:</span>{" "}
            <del className="text-steel-light whitespace-pre-line">{showValue(t, field, change.from)}</del> →{" "}
            <span className="whitespace-pre-line">{showValue(t, field, change.to)}</span>
          </li>
        );
      })}
    </ul>
  );
}

// The requirement as it stood at one version, with the documents current then.
export function VersionView({ projectId, number, label }: { projectId: string; number: number; label: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const { data: version } = useQuery({
    queryKey: ["version", projectId, number],
    queryFn: () => apiFetch<RequirementVersion>(`/projects/${projectId}/versions/${number}`),
    enabled: open,
  });
  return (
    <details className="mt-1 text-[13px]" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)} data-testid={`version-${number}`}>
      <summary className="cursor-pointer text-blue underline w-fit">{label}</summary>
      {version && (
        <div className="border border-border rounded px-3 py-2 mt-1 bg-paper grid gap-1">
          <p className="font-mono text-[11px] text-steel">
            {t("versions.version").replace("{n}", String(version.number))}
            {version.effective_from && ` · ${t("versions.from").replace("{date}", formatDeadline(version.effective_from))}`}
            {version.superseded_at && ` · ${t("versions.until").replace("{date}", formatDeadline(version.superseded_at))}`}
            {version.current && ` · ${t("versions.current")}`}
          </p>
          {!version.complete && <p className="text-xs text-amber-dark">{t("versions.incomplete")}</p>}
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
            {SHOWN_FIELDS.map((f) => (
              <div key={f} className="contents">
                <dt className="text-steel">{t(`versions.field_${f}`)}</dt>
                <dd className="whitespace-pre-line">{showValue(t, f, version.fields[f])}</dd>
              </div>
            ))}
          </dl>
          <p className="text-steel mt-1">{t("versions.documents")}</p>
          <ul className="list-disc ps-5">
            {version.documents.map((d) => (
              <li key={d.id}>
                {d.url ? (
                  <a href={d.url} target="_blank" rel="noreferrer" className="text-blue underline">{d.file_name}</a>
                ) : (
                  d.file_name
                )}
                {d.revision > 1 && ` · v${d.revision}`}
                {!d.is_current && <span className="text-steel-light"> · {t("versions.replacedSince")}</span>}
              </li>
            ))}
            {version.documents.length === 0 && <li className="list-none text-steel-light">—</li>}
          </ul>
        </div>
      )}
    </details>
  );
}

// For a provider whose offer was made before a material change.
export function OutdatedOfferNotice({ project, offer }: { project: ProjectDetail; offer: Offer }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const confirmOffer = useMutation({
    mutationFn: () => apiFetch<Offer>(`/projects/${project.id}/offers/confirm`, { method: "POST" }),
    onSuccess: (data) => {
      setError(null);
      queryClient.setQueryData(["my-offer", project.id], data);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("postPub.error")),
  });
  if (offer.status !== "submitted" || (offer.based_on_material_revision ?? 0) >= (project.material_revision ?? 0)) return null;
  return (
    <div className="border border-amber-dark/40 bg-amber/10 rounded px-4 py-3 mb-4 text-sm">
      <strong className="font-display text-navy block">{t("postPub.outdatedHeading")}</strong>
      <p className="text-steel">{t("postPub.outdatedBody")}</p>
      <VersionView
        projectId={project.id}
        number={offer.based_on_material_revision ?? 0}
        label={t("versions.yourOfferVersion").replace("{n}", String(offer.based_on_material_revision ?? 0))}
      />
      <ErrorBanner message={error} />
      <button type="button" onClick={() => confirmOffer.mutate()} disabled={confirmOffer.isPending} className="mt-2 bg-navy hover:bg-navy-deep text-white text-xs font-semibold rounded px-4 py-2">
        {t("postPub.confirmOffer")}
      </button>
    </div>
  );
}
