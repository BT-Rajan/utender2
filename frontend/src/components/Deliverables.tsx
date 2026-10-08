import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { Agreement, Milestone } from "@/components/AgreementPanel";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface RequirementItem {
  id: string;
  position: number;
  description: string;
}

type Action = { id: string; verb: "deliver" | "accept" | "return"; note: string };

// Stage 7.7: the agreement's deliverables, where the work has them. The owner
// side sets them out while the agreement is being prepared (optionally from
// the requirement's own items); once it is in force they stay as agreed. The
// winning provider delivers each, with evidence; the owner side accepts it or
// returns it for correction. A simple job has none, and shows nothing here
// unless its owner adds some while preparing.
export function Deliverables({
  projectId, agreement: a, onDone, onFailed,
}: { projectId: string; agreement: Agreement; onDone: (next: Agreement) => void; onFailed: (e: Error) => void }) {
  const { t, language } = useI18n();
  const base = `/projects/${projectId}/agreement/milestones`;
  const owner = a.side === "owner";
  const provider = a.side === "provider";
  const settingOut = owner && a.status === "preparing";
  const [draft, setDraft] = useState<{ title: string; description: string; due_date: string; project_item_id: string } | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [evidence, setEvidence] = useState<{ id: string; file: File | null } | null>(null);
  const { data: requirement } = useQuery({
    queryKey: ["agreement-items", projectId],
    queryFn: () => apiFetch<{ items: RequirementItem[] }>(`/projects/${projectId}`),
    enabled: settingOut && draft !== null,
  });
  const after = (next: Agreement) => { setDraft(null); setAction(null); setEvidence(null); onDone(next); };
  const failed = (e: Error) => { setAction(null); setEvidence(null); onFailed(e); };
  const add = useMutation({
    mutationFn: (d: NonNullable<typeof draft>) =>
      apiFetch<Agreement>(base, {
        method: "POST",
        body: { title: d.title, description: d.description || null, due_date: d.due_date || null, project_item_id: d.project_item_id || null },
        headers: { "If-Match": String(a.version) },
      }),
    onSuccess: after,
    onError: failed,
  });
  const remove = useMutation({
    mutationFn: (m: Milestone) => apiFetch<Agreement>(`${base}/${m.id}`, { method: "DELETE", headers: { "If-Match": String(m.version) } }),
    onSuccess: after,
    onError: failed,
  });
  const act = useMutation({
    mutationFn: (x: Action & { version: number }) =>
      apiFetch<Agreement>(`${base}/${x.id}/${x.verb}`, { method: "POST", body: { note: x.note || null }, headers: { "If-Match": String(x.version) } }),
    onSuccess: after,
    onError: failed,
  });
  const attach = useMutation({
    mutationFn: (x: { id: string; file: File }) => {
      const form = new FormData();
      form.append("kind", "other");
      form.append("milestone_id", x.id);
      form.append("file", x.file);
      return apiFetch<Agreement>(`/projects/${projectId}/agreement/documents`, { method: "POST", formData: form });
    },
    onSuccess: after,
    onError: failed,
  });

  if (a.milestones.length === 0 && !settingOut) return null;
  const d = "deliverables";
  const busy = add.isPending || remove.isPending || act.isPending || attach.isPending;
  const working = a.execution_status === "in_progress";
  const tone = { pending: "text-steel", delivered: "text-amber-dark", accepted: "text-green", returned: "text-red" } as const;

  return (
    <div className="border-t border-border mt-4 pt-3" data-testid="deliverables">
      <div className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t(`${d}.heading`)}</div>
      <p className="text-xs text-steel mb-2">{t(settingOut ? `${d}.helpPreparing` : `${d}.help`)}</p>
      <ol className="grid gap-2">
        {a.milestones.map((m) => {
          const docs = a.documents.filter((doc) => doc.milestone_id === m.id);
          const open = action?.id === m.id ? action : null;
          return (
            <li key={m.id} className="border border-border rounded px-3 py-2" data-testid="deliverable">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-semibold" dir="auto">{m.position}. {m.title}</span>
                <span className={`font-mono text-[11px] font-semibold ${tone[m.status]}`}>{t(`${d}.status.${m.status}`)}</span>
              </div>
              {m.project_item_label && <div className="text-xs text-steel" dir="auto">{t(`${d}.fromItem`)}: {m.project_item_label}</div>}
              {m.description && <p className="text-[13px] whitespace-pre-wrap break-words" dir="auto">{m.description}</p>}
              <div className="text-xs text-steel mt-0.5">
                {t(`${d}.due`)}: {m.due_date ? fullDate(`${m.due_date}T12:00:00Z`, language, false) : "—"}
                {m.delivered_at && <> · {t(`${d}.deliveredOn`)} {fullDate(m.delivered_at, language)}</>}
                {m.decided_at && <> · {t(`${d}.decidedOn.${m.status === "accepted" ? "accepted" : "returned"}`)} {fullDate(m.decided_at, language)}</>}
              </div>
              {m.delivery_note && <p className="text-xs mt-0.5" dir="auto">{t(`${d}.deliveryNote`)}: {m.delivery_note}</p>}
              {m.decision_note && <p className="text-xs mt-0.5" dir="auto">{t(`${d}.decisionNote`)}: {m.decision_note}</p>}
              {docs.length > 0 && (
                <ul className="mt-1 grid gap-0.5">
                  {docs.map((doc) => (
                    <li key={doc.id} className="text-xs">
                      <a href={doc.url} target="_blank" rel="noopener noreferrer" className="text-blue underline break-all">{doc.file_name}</a>
                      <span className="text-steel"> · {fullDate(doc.uploaded_at, language)}</span>
                    </li>
                  ))}
                </ul>
              )}

              {open ? (
                <form
                  className="grid gap-1 mt-2 max-w-md"
                  onSubmit={(ev) => { ev.preventDefault(); act.mutate({ ...open, note: open.note.trim(), version: m.version }); }}
                >
                  <label className="grid gap-0.5 text-xs text-steel" htmlFor={`deliverable-note-${m.id}`}>
                    {t(`${d}.noteLabel.${open.verb}`)}
                    <textarea id={`deliverable-note-${m.id}`} value={open.note} onChange={(ev) => setAction({ ...open, note: ev.target.value })} maxLength={2000} rows={2} dir="auto" className="border border-border rounded px-2 py-1 text-sm text-ink" />
                  </label>
                  <div className="flex gap-2">
                    <button type="submit" disabled={busy || (open.verb === "return" && !open.note.trim())} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">
                      {t(`${d}.submit.${open.verb}`)}
                    </button>
                    <button type="button" onClick={() => setAction(null)} className="text-xs text-steel underline">{t("agreement.cancel")}</button>
                  </div>
                </form>
              ) : (
                <div className="flex flex-wrap gap-3 mt-1">
                  {provider && working && (m.status === "pending" || m.status === "returned") && (
                    <button type="button" disabled={busy} onClick={() => setAction({ id: m.id, verb: "deliver", note: "" })} className="text-xs text-blue underline" data-testid="deliverable-deliver">{t(`${d}.deliver`)}</button>
                  )}
                  {owner && m.status === "delivered" && a.status !== "terminated" && (
                    <>
                      <button type="button" disabled={busy} onClick={() => setAction({ id: m.id, verb: "accept", note: "" })} className="text-xs text-green underline" data-testid="deliverable-accept">{t(`${d}.accept`)}</button>
                      <button type="button" disabled={busy} onClick={() => setAction({ id: m.id, verb: "return", note: "" })} className="text-xs text-red underline" data-testid="deliverable-return">{t(`${d}.return`)}</button>
                    </>
                  )}
                  {(owner || provider) && m.status !== "accepted" && a.status !== "terminated" && (
                    evidence?.id === m.id ? (
                      <form className="flex flex-wrap items-center gap-2" onSubmit={(ev) => { ev.preventDefault(); if (evidence.file) attach.mutate({ id: m.id, file: evidence.file }); }}>
                        <label className="text-xs text-steel" htmlFor={`deliverable-file-${m.id}`}>{t(`${d}.evidenceFile`)}</label>
                        <input id={`deliverable-file-${m.id}`} type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.dwg" onChange={(ev) => setEvidence({ id: m.id, file: ev.target.files?.[0] ?? null })} className="text-xs" />
                        <button type="submit" disabled={!evidence.file || busy} className="bg-navy text-white text-xs font-semibold rounded px-2 py-1 disabled:opacity-60">{t("agreement.attach")}</button>
                        <button type="button" onClick={() => setEvidence(null)} className="text-xs text-steel underline">{t("agreement.cancel")}</button>
                      </form>
                    ) : (
                      <button type="button" disabled={busy} onClick={() => setEvidence({ id: m.id, file: null })} className="text-xs text-blue underline">{t(`${d}.addEvidence`)}</button>
                    )
                  )}
                  {settingOut && m.status === "pending" && docs.length === 0 && (
                    <button type="button" disabled={busy} onClick={() => remove.mutate(m)} className="text-xs text-red underline">{t("agreement.remove")}</button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      {settingOut && (draft ? (
        <form className="grid gap-2 mt-3 max-w-md" onSubmit={(ev) => { ev.preventDefault(); add.mutate({ ...draft, title: draft.title.trim() }); }}>
          {(requirement?.items.length ?? 0) > 0 && (
            <label className="grid gap-0.5 text-xs text-steel" htmlFor="deliverable-item">
              {t(`${d}.fromItemLabel`)}
              <select
                id="deliverable-item"
                value={draft.project_item_id}
                onChange={(ev) => {
                  const item = requirement?.items.find((i) => i.id === ev.target.value);
                  setDraft({ ...draft, project_item_id: ev.target.value, title: draft.title || (item ? item.description.slice(0, 200) : "") });
                }}
                className="border border-border rounded px-2 py-1 text-sm text-ink"
              >
                <option value="">{t(`${d}.noItem`)}</option>
                {requirement?.items.map((i) => <option key={i.id} value={i.id}>{i.position}. {i.description}</option>)}
              </select>
            </label>
          )}
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="deliverable-title">
            {t(`${d}.title`)}
            <input id="deliverable-title" value={draft.title} maxLength={200} dir="auto" onChange={(ev) => setDraft({ ...draft, title: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="deliverable-description">
            {t(`${d}.description`)}
            <textarea id="deliverable-description" value={draft.description} maxLength={4000} rows={2} dir="auto" onChange={(ev) => setDraft({ ...draft, description: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="deliverable-due">
            {t(`${d}.due`)}
            <input id="deliverable-due" type="date" value={draft.due_date} onChange={(ev) => setDraft({ ...draft, due_date: ev.target.value })} className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={busy || !draft.title.trim()} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${d}.add`)}</button>
            <button type="button" onClick={() => setDraft(null)} className="text-xs text-steel underline">{t("agreement.cancel")}</button>
          </div>
        </form>
      ) : (
        <button type="button" disabled={busy} onClick={() => setDraft({ title: "", description: "", due_date: "", project_item_id: "" })} className="mt-2 text-xs text-blue underline" data-testid="deliverable-new">
          {t(`${d}.new`)}
        </button>
      ))}
    </div>
  );
}
