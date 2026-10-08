import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/api/client";
import { Deliverables } from "@/components/Deliverables";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useConfirm } from "@/components/ConfirmDialog";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";
import { money } from "@/lib/money";

export interface AgreementDocument {
  id: string;
  kind: string;
  party: "owner" | "provider";
  file_name: string;
  uploaded_at: string;
  uploaded_by_name: string | null; // Stage 7.4: the viewer's own side's documents only
  milestone_id: string | null; // Stage 7.7: evidence for this deliverable
  url: string;
}

export interface ExecutionUpdate {
  sequence: number;
  kind: "started" | "progress" | "on_hold" | "resumed" | "delivered" | "accepted" | "returned";
  party: "owner" | "provider";
  recorded_by_name: string | null;
  note: string | null;
  created_at: string;
  milestone_id: string | null;
  milestone_title: string | null;
}

export interface Milestone {
  id: string;
  position: number;
  title: string;
  description: string | null;
  due_date: string | null;
  project_item_id: string | null;
  project_item_label: string | null;
  status: "pending" | "delivered" | "accepted" | "returned";
  delivered_at: string | null;
  delivery_note: string | null;
  decided_at: string | null;
  decision_note: string | null;
  version: number;
}

export interface Agreement {
  id: string;
  status: "preparing" | "active" | "terminated";
  reference: string | null;
  effective_date: string | null;
  activated_at: string | null;
  terminated_at: string | null;
  termination_reason: string | null;
  version: number;
  award_id: string;
  awarded_at: string;
  offer_id: string;
  amount: string;
  currency: string;
  owner_name: string | null;
  provider_name: string | null;
  // Stage 7.5: execution
  execution_status: "not_started" | "in_progress" | "on_hold" | "terminated";
  on_hold_since: string | null;
  execution_history: ExecutionUpdate[];
  milestones: Milestone[];
  planned_start_date: string | null;
  planned_start_source: "offer" | "requirement" | null;
  work_started_at: string | null;
  work_started_party: "owner" | "provider" | null;
  work_started_by_name: string | null;
  work_start_note: string | null;
  side: "owner" | "provider" | "admin";
  documents: AgreementDocument[];
}

export const KINDS = ["signed_agreement", "work_order", "purchase_order", "final_quotation", "agreed_scope", "certificate", "other"] as const;

// Stage 7.3: the agreement governing an awarded requirement. The parties agree
// outside U-Tender and attach the papers here; the owner side records when it
// takes effect, or that it was terminated. The award it rests on -- parties,
// value, winning offer -- is the award record's, shown as is.
export function AgreementPanel({ projectId }: { projectId: string }) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const base = `/projects/${projectId}/agreement`;
  const key = ["agreement", projectId];
  const { data: a } = useQuery({ queryKey: key, queryFn: () => apiFetch<Agreement>(base), refetchOnWindowFocus: true, retry: false });
  const [error, setError] = useState<string | null>(null);
  // Stage 7.6 follow-up: a refusal because the agreement moved on (another tab,
  // a colleague, the other party) is explained as a notice once the page has
  // caught up -- not shown as an unexplained error.
  const [notice, setNotice] = useState<string | null>(null);
  const [details, setDetails] = useState<{ reference: string; effective_date: string } | null>(null);
  const [ending, setEnding] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [update, setUpdate] = useState<{ action: "update" | "hold" | "resume"; note: string } | null>(null);
  const [kind, setKind] = useState<string>("signed_agreement");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const done = (next: Agreement) => { setError(null); setNotice(null); queryClient.setQueryData(key, next); };
  const failed = (e: Error) => {
    const refused = e instanceof ApiError && (e.status === 400 || e.status === 409);
    setError(refused ? null : e.message);
    setNotice(refused ? e.message : null);
    setDetails(null); setEnding(null); setStarting(null); setUpdate(null);  // forms opened on the old state
    queryClient.invalidateQueries({ queryKey: key });
  };
  const ifMatch = () => ({ "If-Match": String(a?.version ?? "") });

  const save = useMutation({
    mutationFn: (d: { reference: string; effective_date: string }) =>
      apiFetch<Agreement>(base, { method: "PATCH", body: { reference: d.reference, effective_date: d.effective_date || null }, headers: ifMatch() }),
    onSuccess: (next) => { setDetails(null); done(next); },
    onError: failed,
  });
  const activate = useMutation({
    mutationFn: () => apiFetch<Agreement>(`${base}/activate`, { method: "POST", headers: ifMatch() }),
    onSuccess: done,
    onError: failed,
  });
  const terminate = useMutation({
    mutationFn: (reason: string) => apiFetch<Agreement>(`${base}/terminate`, { method: "POST", body: { reason }, headers: ifMatch() }),
    onSuccess: (next) => { setEnding(null); done(next); },
    onError: failed,
  });
  const startWork = useMutation({
    mutationFn: (note: string) => apiFetch<Agreement>(`${base}/start-work`, { method: "POST", body: { note: note || null }, headers: ifMatch() }),
    onSuccess: (next) => { setStarting(null); done(next); },
    onError: failed,
  });
  const progress = useMutation({
    mutationFn: (u: { action: "update" | "hold" | "resume"; note: string }) =>
      apiFetch<Agreement>(`${base}/progress`, { method: "POST", body: { action: u.action, note: u.note || null }, headers: ifMatch() }),
    onSuccess: (next) => { setUpdate(null); done(next); },
    onError: failed,
  });
  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("kind", kind);
      form.append("file", file as File);
      return apiFetch<Agreement>(`${base}/documents`, { method: "POST", formData: form });
    },
    onSuccess: (next) => { setFile(null); setFileKey((k) => k + 1); done(next); },
    onError: failed,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiFetch<Agreement>(`${base}/documents/${id}`, { method: "DELETE" }),
    onSuccess: done,
    onError: failed,
  });

  if (!a) return null;
  const c = "agreement";
  const owner = a.side === "owner";
  const party = a.side !== "admin";
  const busy = save.isPending || activate.isPending || terminate.isPending || startWork.isPending || progress.isPending;
  const e = "execution";
  const day = (d: string) => fullDate(`${d}T12:00:00Z`, language, false);
  const execTone = a.execution_status === "in_progress" ? "text-green" : a.execution_status === "terminated" ? "text-red" : "text-amber-dark";
  const live = party && (a.execution_status === "in_progress" || a.execution_status === "on_hold");
  const general = a.documents.filter((d) => !d.milestone_id);
  const tone = a.status === "active" ? "text-green" : a.status === "terminated" ? "text-red" : "text-amber-dark";

  return (
    <section className="bg-white border border-border rounded px-5 py-4 mb-5 text-sm" data-testid="agreement">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <div className="font-mono text-[10.5px] uppercase tracking-widest text-navy">{t(`${c}.heading`)}</div>
        <span className={`font-mono text-[11px] font-semibold ${tone}`} data-testid="agreement-status">{t(`${c}.status.${a.status}`)}</span>
      </div>
      <p className="text-xs text-steel mb-2">{t(`${c}.status.${a.status}Help`)}</p>
      <ErrorBanner message={error} />
      {notice && (
        <p role="status" className="text-xs border border-amber-dark/40 bg-amber/10 text-navy rounded px-3 py-2.5 mb-3 max-w-2xl" data-testid="agreement-notice">
          {notice}
        </p>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[13px]">
        <dt className="text-steel">{t(`${c}.owner`)}</dt>
        <dd dir="auto">{a.owner_name ?? "—"}</dd>
        <dt className="text-steel">{t(`${c}.provider`)}</dt>
        <dd dir="auto">{a.provider_name ?? "—"}</dd>
        <dt className="text-steel">{t(`${c}.value`)}</dt>
        <dd className="font-mono text-navy">{money(a.amount, a.currency)}</dd>
        <dt className="text-steel">{t(`${c}.awardedOn`)}</dt>
        <dd>{fullDate(a.awarded_at, language)}</dd>
        <dt className="text-steel">{t(`${c}.effective`)}</dt>
        <dd data-testid="agreement-effective">{a.effective_date ? fullDate(`${a.effective_date}T12:00:00Z`, language, false) : "—"}</dd>
        <dt className="text-steel">{t(`${c}.reference`)}</dt>
        <dd dir="auto">{a.reference ?? "—"}</dd>
        <dt className="text-steel">{t(`${c}.id`)}</dt>
        <dd className="font-mono text-xs break-all">{a.id}</dd>
        {a.status === "terminated" && (
          <>
            <dt className="text-steel">{t(`${c}.terminatedOn`)}</dt>
            <dd>{a.terminated_at && fullDate(a.terminated_at, language)}</dd>
            <dt className="text-steel">{t(`${c}.reason`)}</dt>
            <dd dir="auto" className="whitespace-pre-wrap break-words">{a.termination_reason}</dd>
          </>
        )}
      </dl>

      {owner && a.status === "preparing" && (details ? (
        <form className="grid gap-2 mt-3 max-w-md" onSubmit={(e) => { e.preventDefault(); save.mutate(details); }}>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="agreement-reference">
            {t(`${c}.reference`)}
            <input id="agreement-reference" value={details.reference} maxLength={120} dir="auto" onChange={(e) => setDetails({ ...details, reference: e.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="agreement-effective">
            {t(`${c}.effective`)}
            <input id="agreement-effective" type="date" value={details.effective_date} onChange={(e) => setDetails({ ...details, effective_date: e.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${c}.save`)}</button>
            <button type="button" onClick={() => setDetails(null)} className="text-xs text-steel underline">{t(`${c}.cancel`)}</button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-3 mt-3">
          <button type="button" onClick={() => setDetails({ reference: a.reference ?? "", effective_date: a.effective_date ?? "" })} className="text-xs text-blue underline">{t(`${c}.editDetails`)}</button>
          <button
            type="button"
            disabled={busy || !a.effective_date}
            title={!a.effective_date ? t(`${c}.needsDate`) : undefined}
            onClick={() => void confirm({ title: t(`${c}.activateConfirm`), body: t(`${c}.activateConfirmBody`), confirmLabel: t(`${c}.activate`) }).then((ok) => ok && activate.mutate())}
            className="bg-green text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60"
            data-testid="agreement-activate"
          >
            {t(`${c}.activate`)}
          </button>
        </div>
      ))}
      {owner && a.status !== "terminated" && (ending === null ? (
        <button type="button" disabled={busy} onClick={() => setEnding("")} className="block mt-2 text-xs text-red underline">
          {t(`${c}.terminate`)}
        </button>
      ) : (
        <form className="grid gap-1 mt-3 max-w-md" onSubmit={(e) => { e.preventDefault(); terminate.mutate(ending.trim()); }}>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="agreement-termination">
            {t(`${c}.terminatePrompt`)}
            <textarea id="agreement-termination" value={ending} onChange={(e) => setEnding(e.target.value)} maxLength={2000} rows={2} dir="auto" className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !ending.trim()} className="bg-red text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${c}.terminate`)}</button>
            <button type="button" onClick={() => setEnding(null)} className="text-xs text-steel underline">{t(`${c}.cancel`)}</button>
          </div>
        </form>
      ))}

      {/* Stage 7.5: whether the awarded work has started. */}
      <div className="border-t border-border mt-4 pt-3" data-testid="execution">
        <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
          <div className="font-mono text-[11px] uppercase tracking-wide text-navy">{t(`${e}.heading`)}</div>
          <span className={`font-mono text-[11px] font-semibold ${execTone}`} data-testid="execution-status">{t(`${e}.status.${a.execution_status}`)}</span>
        </div>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[13px]">
          <dt className="text-steel">{t(`${e}.planned`)}</dt>
          <dd>
            {a.planned_start_date ? day(a.planned_start_date) : "—"}
            {a.planned_start_source && <span className="text-xs text-steel"> · {t(`${e}.source.${a.planned_start_source}`)}</span>}
          </dd>
          <dt className="text-steel">{t(`${e}.actual`)}</dt>
          <dd data-testid="execution-started">{a.work_started_at ? fullDate(a.work_started_at, language) : "—"}</dd>
          {a.work_started_party && (
            <>
              <dt className="text-steel">{t(`${e}.recordedBy`)}</dt>
              <dd>{t(`${e}.party.${a.work_started_party}`)}{a.work_started_by_name ? ` (${a.work_started_by_name})` : ""}</dd>
            </>
          )}
          {a.on_hold_since && (
            <>
              <dt className="text-steel">{t(`${e}.onHoldSince`)}</dt>
              <dd>{fullDate(a.on_hold_since, language)}</dd>
            </>
          )}
        </dl>
        {/* Stage 7.6: what the parties recorded since the work started. */}
        {a.execution_history.length > 0 && (
          <ol className="grid gap-1 mt-2 border-s-2 border-border ps-3" data-testid="execution-history">
            {a.execution_history.map((h) => (
              <li key={h.sequence} className="text-[13px]">
                <span className="font-mono text-[10px] text-steel">
                  {fullDate(h.created_at, language)} · {t(`${e}.party.${h.party}`)}{h.recorded_by_name ? ` (${h.recorded_by_name})` : ""}
                </span>
                <div>
                  <span className="font-semibold">{t(`${e}.kind.${h.kind}`)}</span>
                  {h.milestone_title && <span dir="auto"> · {h.milestone_title}</span>}
                  {h.note && <span dir="auto" className="whitespace-pre-wrap break-words"> — {h.note}</span>}
                </div>
              </li>
            ))}
          </ol>
        )}
        {live && (update ? (
          <form className="grid gap-1 mt-2 max-w-md" onSubmit={(ev) => { ev.preventDefault(); progress.mutate({ ...update, note: update.note.trim() }); }}>
            <label className="grid gap-0.5 text-xs text-steel" htmlFor="execution-progress-note">
              {t(update.action === "update" ? `${e}.progressLabel` : `${e}.noteLabel`)}
              <textarea id="execution-progress-note" value={update.note} onChange={(ev) => setUpdate({ ...update, note: ev.target.value })} maxLength={2000} rows={2} dir="auto" className="border border-border rounded px-2 py-1 text-sm text-ink" />
            </label>
            <div className="flex gap-2">
              <button type="submit" disabled={busy || (update.action === "update" && !update.note.trim())} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">
                {t(`${e}.submit.${update.action}`)}
              </button>
              <button type="button" onClick={() => setUpdate(null)} className="text-xs text-steel underline">{t(`${c}.cancel`)}</button>
            </div>
          </form>
        ) : (
          <div className="flex flex-wrap gap-3 mt-2">
            <button type="button" disabled={busy} onClick={() => setUpdate({ action: "update", note: "" })} className="text-xs text-blue underline" data-testid="execution-update">{t(`${e}.addUpdate`)}</button>
            {a.execution_status === "in_progress" ? (
              <button type="button" disabled={busy} onClick={() => setUpdate({ action: "hold", note: "" })} className="text-xs text-amber-dark underline" data-testid="execution-hold">{t(`${e}.hold`)}</button>
            ) : (
              <button type="button" disabled={busy} onClick={() => setUpdate({ action: "resume", note: "" })} className="text-xs text-green underline" data-testid="execution-resume">{t(`${e}.resume`)}</button>
            )}
          </div>
        ))}
        {party && a.execution_status === "not_started" && (starting === null ? (
          <>
            <p className="text-xs text-steel mt-2">{t(`${e}.next`)}</p>
            <button type="button" disabled={busy} onClick={() => setStarting("")} className="mt-1 bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60" data-testid="execution-start">
              {t(`${e}.start`)}
            </button>
          </>
        ) : (
          <form className="grid gap-1 mt-2 max-w-md" onSubmit={(ev) => { ev.preventDefault(); startWork.mutate(starting.trim()); }}>
            <label className="grid gap-0.5 text-xs text-steel" htmlFor="execution-note">
              {t(`${e}.noteLabel`)}
              <textarea id="execution-note" value={starting} onChange={(ev) => setStarting(ev.target.value)} maxLength={2000} rows={2} dir="auto" className="border border-border rounded px-2 py-1 text-sm text-ink" />
            </label>
            <p className="text-xs text-steel">{t(`${e}.confirmHelp`)}</p>
            <div className="flex gap-2">
              <button type="submit" disabled={busy} className="bg-green text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${e}.confirm`)}</button>
              <button type="button" onClick={() => setStarting(null)} className="text-xs text-steel underline">{t(`${c}.cancel`)}</button>
            </div>
          </form>
        ))}
      </div>

      <Deliverables projectId={projectId} agreement={a} onDone={done} onFailed={failed} />

      <div className="font-mono text-[11px] uppercase tracking-wide text-navy mt-4 mb-1">{t(`${c}.documents`)}</div>
      {general.length === 0 ? (
        <p className="text-xs text-steel">{t(`${c}.noDocuments`)}</p>
      ) : (
        <ul className="grid gap-1" data-testid="agreement-documents">
          {general.map((d) => (
            <li key={d.id} className="flex flex-wrap items-baseline gap-x-3">
              <a href={d.url} target="_blank" rel="noopener noreferrer" className="text-blue underline break-all">{d.file_name}</a>
              <span className="font-mono text-[10px] text-steel">
                {t(`${c}.kind.${d.kind}`)} · {t(`${c}.by.${d.party}`)}{d.uploaded_by_name ? ` (${d.uploaded_by_name})` : ""} · {fullDate(d.uploaded_at, language)}
              </span>
              {a.status === "preparing" && d.party === a.side && (
                <button type="button" onClick={() => remove.mutate(d.id)} disabled={remove.isPending} className="text-xs text-red underline">{t(`${c}.remove`)}</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {party && a.status !== "terminated" && (
        <form className="flex flex-wrap items-end gap-2 mt-2" onSubmit={(e) => { e.preventDefault(); if (file) upload.mutate(); }}>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="agreement-kind">
            {t(`${c}.kindLabel`)}
            <select id="agreement-kind" value={kind} onChange={(e) => setKind(e.target.value)} className="border border-border rounded px-2 py-1 text-sm text-ink">
              {KINDS.map((k) => <option key={k} value={k}>{t(`${c}.kind.${k}`)}</option>)}
            </select>
          </label>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="agreement-file">
            {t(`${c}.file`)}
            <input key={fileKey} id="agreement-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.dwg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs" />
          </label>
          <button type="submit" disabled={!file || upload.isPending} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${c}.attach`)}</button>
        </form>
      )}
    </section>
  );
}
