import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { EVIDENCE_KINDS, type Agreement, type AgreementDocument } from "@/components/AgreementPanel";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

// Stage 7.9: one piece of evidence -- what it is, from which side (and member,
// for one's own side), when -- opened through the authorised link.
export function EvidenceList({ docs }: { docs: AgreementDocument[] }) {
  const { t, language } = useI18n();
  if (docs.length === 0) return null;
  return (
    <ul className="grid gap-0.5 mt-0.5" data-testid="evidence-list">
      {docs.map((d) => (
        <li key={d.id} className="text-xs">
          <a href={d.url} target="_blank" rel="noopener noreferrer" className="text-blue underline break-all">{d.file_name}</a>
          <span className="font-mono text-[10px] text-steel">
            {" "}· {t(`agreement.kind.${d.kind}`)} · {t(`agreement.by.${d.party}`)}{d.uploaded_by_name ? ` (${d.uploaded_by_name})` : ""} · {fullDate(d.uploaded_at, language)}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Stage 7.9: execution evidence -- photographs, site, delivery, completion and
// inspection reports, test results -- for the transaction as a whole or for
// one progress update. Deliverables carry their own. Once the work has
// started, either party adds it; it changes no status.
export function Evidence({
  projectId, agreement: a, onDone, onFailed,
}: { projectId: string; agreement: Agreement; onDone: (next: Agreement) => void; onFailed: (e: Error) => void }) {
  const { t, language } = useI18n();
  const [kind, setKind] = useState<string>("progress_photo");
  const [related, setRelated] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("kind", kind);
      if (related) form.append("execution_update_id", related);
      form.append("file", file as File);
      return apiFetch<Agreement>(`/projects/${projectId}/agreement/documents`, { method: "POST", formData: form });
    },
    onSuccess: (next) => { setFile(null); setRelated(""); setFileKey((k) => k + 1); onDone(next); },
    onError: onFailed,
  });

  const started = a.work_started_at !== null;
  const general = a.documents.filter((d) => d.evidence && !d.milestone_id && !d.execution_update_id);
  const canAdd = a.side !== "admin" && started && a.status !== "terminated";
  if (!started) return null;
  const x = "evidence";
  // Progress updates, and the whole work's completion submissions (Stage 7.10).
  const updates = a.execution_history.filter((h) => ["started", "progress", "on_hold", "resumed"].includes(h.kind) || (h.kind === "delivered" && !h.milestone_id));

  return (
    <div className="border-t border-border mt-4 pt-3" data-testid="evidence">
      <div className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t(`${x}.heading`)}</div>
      <p className="text-xs text-steel mb-1">{t(`${x}.help`)}</p>
      {general.length === 0 ? <p className="text-xs text-steel">{t(`${x}.none`)}</p> : <EvidenceList docs={general} />}
      {canAdd && (
        <form className="flex flex-wrap items-end gap-2 mt-2" onSubmit={(ev) => { ev.preventDefault(); if (file) upload.mutate(); }}>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="evidence-kind">
            {t(`${x}.kind`)}
            <select id="evidence-kind" value={kind} onChange={(ev) => setKind(ev.target.value)} className="border border-border rounded px-2 py-1 text-sm text-ink">
              {EVIDENCE_KINDS.map((k) => <option key={k} value={k}>{t(`agreement.kind.${k}`)}</option>)}
            </select>
          </label>
          {updates.length > 0 && (
            <label className="grid gap-0.5 text-xs text-steel" htmlFor="evidence-related">
              {t(`${x}.relatesTo`)}
              <select id="evidence-related" value={related} onChange={(ev) => setRelated(ev.target.value)} className="border border-border rounded px-2 py-1 text-sm text-ink max-w-[16rem]">
                <option value="">{t(`${x}.wholeWork`)}</option>
                {updates.map((h) => (
                  <option key={h.id} value={h.id}>
                    {fullDate(h.created_at, language)} · {h.kind === "delivered" ? t("completion.history.delivered") : t(`execution.kind.${h.kind}`)}{h.note ? ` — ${h.note.slice(0, 40)}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="evidence-file">
            {t("agreement.file")}
            <input key={fileKey} id="evidence-file" type="file" accept=".pdf,.jpg,.jpeg,.png,.docx,.xlsx,.dwg" onChange={(ev) => setFile(ev.target.files?.[0] ?? null)} className="text-xs" />
          </label>
          <button type="submit" disabled={!file || upload.isPending} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${x}.add`)}</button>
        </form>
      )}
    </div>
  );
}
