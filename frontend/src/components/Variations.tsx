import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { Agreement, Variation } from "@/components/AgreementPanel";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";
import { money } from "@/lib/money";

type Draft = { description: string; value_change: string; completion_date: string; milestone_id: string; milestone_due_date: string; add_deliverable: string };
const EMPTY: Draft = { description: "", value_change: "", completion_date: "", milestone_id: "", milestone_due_date: "", add_deliverable: "" };

// Stage 7.8: changes to the work once the agreement is in force. Either party
// proposes; it takes effect only when the other party agrees. The original
// award and agreement stay as they were; each change shows what it changed
// from and to.
export function Variations({
  projectId, agreement: a, onDone, onFailed,
}: { projectId: string; agreement: Agreement; onDone: (next: Agreement) => void; onFailed: (e: Error) => void }) {
  const { t, language } = useI18n();
  const base = `/projects/${projectId}/agreement/variations`;
  const party = a.side !== "admin";
  const [draft, setDraft] = useState<Draft | null>(null);
  const [answer, setAnswer] = useState<{ id: string; verb: "agree" | "reject"; note: string } | null>(null);
  const [paper, setPaper] = useState<{ id: string; file: File | null } | null>(null);
  const after = (next: Agreement) => { setDraft(null); setAnswer(null); setPaper(null); onDone(next); };
  const failed = (e: Error) => { setAnswer(null); setPaper(null); onFailed(e); };
  const propose = useMutation({
    mutationFn: (d: Draft) =>
      apiFetch<Agreement>(base, {
        method: "POST",
        headers: { "If-Match": String(a.version) },
        body: {
          description: d.description,
          value_change: d.value_change || null,
          completion_date: d.completion_date || null,
          milestone_id: d.milestone_id || null,
          milestone_due_date: d.milestone_id ? d.milestone_due_date || null : null,
          add_deliverable: d.add_deliverable || null,
        },
      }),
    onSuccess: after,
    onError: failed,
  });
  const act = useMutation({
    mutationFn: (x: { v: Variation; verb: "agree" | "reject" | "withdraw"; note?: string }) =>
      apiFetch<Agreement>(`${base}/${x.v.id}/${x.verb}`, {
        method: "POST",
        headers: { "If-Match": String(x.v.version) },
        body: x.verb === "withdraw" ? undefined : { note: x.note || null },
      }),
    onSuccess: after,
    onError: failed,
  });
  const attach = useMutation({
    mutationFn: (x: { id: string; file: File }) => {
      const form = new FormData();
      form.append("kind", "change_order");
      form.append("variation_id", x.id);
      form.append("file", x.file);
      return apiFetch<Agreement>(`/projects/${projectId}/agreement/documents`, { method: "POST", formData: form });
    },
    onSuccess: after,
    onError: failed,
  });

  const inForce = a.status === "active";
  if (a.variations.length === 0 && !(party && inForce)) return null;
  const v8 = "variations";
  const open = a.variations.some((x) => x.status === "proposed");
  const busy = propose.isPending || act.isPending || attach.isPending;
  const day = (d: string) => fullDate(`${d}T12:00:00Z`, language, false);
  const tone = { proposed: "text-amber-dark", agreed: "text-green", rejected: "text-red", withdrawn: "text-steel", lapsed: "text-steel" } as const;
  const reschedulable = a.milestones.filter((m) => m.status !== "accepted");

  return (
    <div className="border-t border-border mt-4 pt-3" data-testid="variations">
      <div className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t(`${v8}.heading`)}</div>
      <p className="text-xs text-steel mb-2">{t(`${v8}.help`)}</p>
      <ol className="grid gap-2">
        {a.variations.map((v) => {
          const papers = a.documents.filter((d) => d.variation_id === v.id);
          const mine = v.proposed_party === a.side;
          const answering = answer?.id === v.id ? answer : null;
          return (
            <li key={v.id} className="border border-border rounded px-3 py-2" data-testid="variation">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-semibold">{t(`${v8}.label`).replace("{n}", String(v.number))}</span>
                <span className={`font-mono text-[11px] font-semibold ${tone[v.status]}`}>{t(`${v8}.status.${v.status}`)}</span>
              </div>
              <p className="text-[13px] whitespace-pre-wrap break-words" dir="auto">{v.description}</p>
              <ul className="text-xs mt-1 grid gap-0.5">
                {v.value_change && (
                  <li>
                    {t(`${v8}.valueChange`)}: <span className="font-mono">{Number(v.value_change) > 0 ? "+" : ""}{money(v.value_change, a.currency)}</span>
                    {v.previous_amount && v.resulting_amount && <span className="text-steel"> ({money(v.previous_amount, a.currency)} → {money(v.resulting_amount, a.currency)})</span>}
                  </li>
                )}
                {v.completion_date && (
                  <li>{t(`${v8}.completion`)}: {v.previous_completion_date && <span className="text-steel">{day(v.previous_completion_date)} → </span>}{day(v.completion_date)}</li>
                )}
                {v.milestone_due_date && (
                  <li dir="auto">
                    {t(`${v8}.deliverableDue`).replace("{title}", v.milestone_title ?? "—")}: {v.previous_milestone_due_date && <span className="text-steel">{day(v.previous_milestone_due_date)} → </span>}{day(v.milestone_due_date)}
                  </li>
                )}
                {v.add_deliverable && <li dir="auto">{t(`${v8}.adds`)}: {v.add_deliverable}</li>}
              </ul>
              <div className="font-mono text-[10px] text-steel mt-1">
                {t(`${v8}.proposedBy.${v.proposed_party}`)} · {fullDate(v.proposed_at, language)}
                {v.decided_at && v.decided_party && <> · {t(`${v8}.decided.${v.status}`)} {t(`execution.party.${v.decided_party}`)} · {fullDate(v.decided_at, language)}</>}
              </div>
              {v.decision_note && <p className="text-xs mt-0.5" dir="auto">{t(`${v8}.note`)}: {v.decision_note}</p>}
              {papers.length > 0 && (
                <ul className="mt-1 grid gap-0.5">
                  {papers.map((d) => (
                    <li key={d.id} className="text-xs">
                      <a href={d.url} target="_blank" rel="noopener noreferrer" className="text-blue underline break-all">{d.file_name}</a>
                      <span className="text-steel"> · {fullDate(d.uploaded_at, language)}</span>
                    </li>
                  ))}
                </ul>
              )}
              {party && v.status === "proposed" && (answering ? (
                <form className="grid gap-1 mt-2 max-w-md" onSubmit={(ev) => { ev.preventDefault(); act.mutate({ v, verb: answering.verb, note: answering.note.trim() }); }}>
                  <label className="grid gap-0.5 text-xs text-steel" htmlFor={`variation-note-${v.id}`}>
                    {t(`${v8}.noteLabel`)}
                    <textarea id={`variation-note-${v.id}`} value={answering.note} onChange={(ev) => setAnswer({ ...answering, note: ev.target.value })} maxLength={2000} rows={2} dir="auto" className="border border-border rounded px-2 py-1 text-sm text-ink" />
                  </label>
                  {answering.verb === "agree" && <p className="text-xs text-steel">{t(`${v8}.agreeHelp`)}</p>}
                  <div className="flex gap-2">
                    <button type="submit" disabled={busy} className={`${answering.verb === "agree" ? "bg-green" : "bg-red"} text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60`}>
                      {t(`${v8}.${answering.verb}`)}
                    </button>
                    <button type="button" onClick={() => setAnswer(null)} className="text-xs text-steel underline">{t("agreement.cancel")}</button>
                  </div>
                </form>
              ) : (
                <div className="flex flex-wrap gap-3 mt-1">
                  {mine ? (
                    <>
                      <span className="text-xs text-steel">{t(`${v8}.awaiting`)}</span>
                      <button type="button" disabled={busy} onClick={() => act.mutate({ v, verb: "withdraw" })} className="text-xs text-red underline">{t(`${v8}.withdraw`)}</button>
                    </>
                  ) : (
                    <>
                      <button type="button" disabled={busy} onClick={() => setAnswer({ id: v.id, verb: "agree", note: "" })} className="text-xs text-green underline" data-testid="variation-agree">{t(`${v8}.agree`)}</button>
                      <button type="button" disabled={busy} onClick={() => setAnswer({ id: v.id, verb: "reject", note: "" })} className="text-xs text-red underline" data-testid="variation-reject">{t(`${v8}.reject`)}</button>
                    </>
                  )}
                </div>
              ))}
              {party && !["terminated", "completed"].includes(a.status) && (v.status === "proposed" || v.status === "agreed") && (
                paper?.id === v.id ? (
                  <form className="flex flex-wrap items-center gap-2 mt-1" onSubmit={(ev) => { ev.preventDefault(); if (paper.file) attach.mutate({ id: v.id, file: paper.file }); }}>
                    <label className="text-xs text-steel" htmlFor={`variation-file-${v.id}`}>{t(`${v8}.paper`)}</label>
                    <input id={`variation-file-${v.id}`} type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.dwg" onChange={(ev) => setPaper({ id: v.id, file: ev.target.files?.[0] ?? null })} className="text-xs" />
                    <button type="submit" disabled={!paper.file || busy} className="bg-navy text-white text-xs font-semibold rounded px-2 py-1 disabled:opacity-60">{t("agreement.attach")}</button>
                    <button type="button" onClick={() => setPaper(null)} className="text-xs text-steel underline">{t("agreement.cancel")}</button>
                  </form>
                ) : (
                  <button type="button" disabled={busy} onClick={() => setPaper({ id: v.id, file: null })} className="mt-1 text-xs text-blue underline">{t(`${v8}.addPaper`)}</button>
                )
              )}
            </li>
          );
        })}
      </ol>

      {party && inForce && !open && (draft ? (
        <form className="grid gap-2 mt-3 max-w-md" onSubmit={(ev) => { ev.preventDefault(); propose.mutate({ ...draft, description: draft.description.trim(), add_deliverable: draft.add_deliverable.trim() }); }}>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="variation-description">
            {t(`${v8}.description`)}
            <textarea id="variation-description" value={draft.description} maxLength={4000} rows={3} dir="auto" onChange={(ev) => setDraft({ ...draft, description: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="variation-value">
            {t(`${v8}.valueChangeLabel`).replace("{currency}", a.currency)}
            <input id="variation-value" type="number" step="0.001" value={draft.value_change} onChange={(ev) => setDraft({ ...draft, value_change: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="variation-completion">
            {t(`${v8}.completionLabel`)}
            <input id="variation-completion" type="date" value={draft.completion_date} onChange={(ev) => setDraft({ ...draft, completion_date: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          {reschedulable.length > 0 && (
            <div className="grid grid-cols-[1fr_auto] gap-2">
              <label className="grid gap-0.5 text-xs text-steel" htmlFor="variation-milestone">
                {t(`${v8}.rescheduleLabel`)}
                <select id="variation-milestone" value={draft.milestone_id} onChange={(ev) => setDraft({ ...draft, milestone_id: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink">
                  <option value="">—</option>
                  {reschedulable.map((m) => <option key={m.id} value={m.id}>{m.position}. {m.title}</option>)}
                </select>
              </label>
              <label className="grid gap-0.5 text-xs text-steel" htmlFor="variation-milestone-due">
                {t(`${v8}.newDue`)}
                <input id="variation-milestone-due" type="date" disabled={!draft.milestone_id} value={draft.milestone_due_date} onChange={(ev) => setDraft({ ...draft, milestone_due_date: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
              </label>
            </div>
          )}
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="variation-add">
            {t(`${v8}.addLabel`)}
            <input id="variation-add" value={draft.add_deliverable} maxLength={200} dir="auto" onChange={(ev) => setDraft({ ...draft, add_deliverable: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <p className="text-xs text-steel">{t(`${v8}.proposeHelp`)}</p>
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !draft.description.trim()} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${v8}.propose`)}</button>
            <button type="button" onClick={() => setDraft(null)} className="text-xs text-steel underline">{t("agreement.cancel")}</button>
          </div>
        </form>
      ) : (
        <button type="button" disabled={busy} onClick={() => setDraft(EMPTY)} className="mt-2 text-xs text-blue underline" data-testid="variation-new">{t(`${v8}.new`)}</button>
      ))}
    </div>
  );
}
