import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { Agreement } from "@/components/AgreementPanel";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

// Stage 7.10: the whole work's completion. Once every deliverable is
// accepted, the service provider submits the work as complete; the owner
// accepts it or returns it for correction. Submitted is not accepted.
export function Completion({
  projectId, agreement: a, onDone, onFailed,
}: { projectId: string; agreement: Agreement; onDone: (next: Agreement) => void; onFailed: (e: Error) => void }) {
  const { t, language } = useI18n();
  const [open, setOpen] = useState<{ verb: "submit" | "accept" | "return"; note: string } | null>(null);
  const act = useMutation({
    mutationFn: (x: { verb: "submit" | "accept" | "return"; note: string }) =>
      apiFetch<Agreement>(`/projects/${projectId}/agreement/completion/${x.verb}`, {
        method: "POST", body: { note: x.note || null }, headers: { "If-Match": String(a.version) },
      }),
    onSuccess: (next) => { setOpen(null); onDone(next); },
    onError: (e: Error) => { setOpen(null); onFailed(e); },
  });

  if (a.work_started_at === null) return null;
  const c = "completion";
  const status = a.completion_status ?? "none";
  const live = a.status !== "terminated";
  const openChange = a.variations.some((v) => v.status === "proposed");
  const canSubmit = a.side === "provider" && live && a.execution_status === "in_progress" && (status === "none" || status === "returned")
    && a.outstanding_deliverables === 0 && !openChange;
  const canDecide = a.side === "owner" && live && status === "submitted";
  const tone = { none: "text-steel", submitted: "text-amber-dark", returned: "text-red", accepted: "text-green" }[status];

  return (
    <div className="border-t border-border mt-4 pt-3" data-testid="completion">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <div className="font-mono text-[11px] uppercase tracking-wide text-navy">{t(`${c}.heading`)}</div>
        <span className={`font-mono text-[11px] font-semibold ${tone}`} data-testid="completion-status">{t(`${c}.status.${status}`)}</span>
      </div>
      {a.outstanding_deliverables > 0 && status !== "accepted" && (
        <p className="text-xs text-steel">{t(`${c}.outstanding`).replace("{n}", String(a.outstanding_deliverables))}</p>
      )}
      {openChange && status !== "accepted" && <p className="text-xs text-steel">{t(`${c}.openChange`)}</p>}
      {a.completion_submitted_at && (
        <p className="text-xs mt-0.5">
          {t(`${c}.submittedOn`)} {fullDate(a.completion_submitted_at, language)}
          {a.completion_note && <span dir="auto"> — {a.completion_note}</span>}
        </p>
      )}
      {a.completion_decided_at && (
        <p className="text-xs mt-0.5">
          {t(`${c}.decidedOn.${status === "accepted" ? "accepted" : "returned"}`)} {fullDate(a.completion_decided_at, language)}
          {a.completion_decision_note && <span dir="auto"> — {a.completion_decision_note}</span>}
        </p>
      )}
      {status === "accepted" && <p className="text-xs text-steel mt-1">{t(`${c}.acceptedHelp`)}</p>}

      {open ? (
        <form className="grid gap-1 mt-2 max-w-md" onSubmit={(ev) => { ev.preventDefault(); act.mutate({ ...open, note: open.note.trim() }); }}>
          <label className="grid gap-0.5 text-xs text-steel" htmlFor="completion-note">
            {t(`${c}.noteLabel.${open.verb}`)}
            <textarea id="completion-note" value={open.note} onChange={(ev) => setOpen({ ...open, note: ev.target.value })} maxLength={2000} rows={2} dir="auto" className="border border-border rounded px-2 py-1 text-sm text-ink" />
          </label>
          <p className="text-xs text-steel">{t(`${c}.confirmHelp.${open.verb}`)}</p>
          <div className="flex gap-2">
            <button type="submit" disabled={act.isPending || (open.verb === "return" && !open.note.trim())} className={`${open.verb === "return" ? "bg-red" : open.verb === "accept" ? "bg-green" : "bg-navy"} text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60`}>
              {t(`${c}.do.${open.verb}`)}
            </button>
            <button type="button" onClick={() => setOpen(null)} className="text-xs text-steel underline">{t("agreement.cancel")}</button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-3 mt-2">
          {canSubmit && (
            <button type="button" onClick={() => setOpen({ verb: "submit", note: "" })} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5" data-testid="completion-submit">
              {t(`${c}.do.submit`)}
            </button>
          )}
          {canDecide && (
            <>
              <button type="button" onClick={() => setOpen({ verb: "accept", note: "" })} className="bg-green text-white text-xs font-semibold rounded px-3 py-1.5" data-testid="completion-accept">{t(`${c}.do.accept`)}</button>
              <button type="button" onClick={() => setOpen({ verb: "return", note: "" })} className="text-xs text-red underline" data-testid="completion-return">{t(`${c}.do.return`)}</button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
