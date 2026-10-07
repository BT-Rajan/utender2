import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { EvaluationNote } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

const token = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

// Stage 6.11: the owner side's private evaluation notes -- on one offer, or on
// the requirement as a whole. Only the owner side reads them; each author
// edits or removes their own. Plain notes: nothing here scores or ranks.
export function EvaluationNotes({ projectId, offerId }: { projectId: string; offerId?: string }) {
  const { t, language } = useI18n();
  const queryClient = useQueryClient();
  const base = `/owner/projects/${projectId}/notes`;
  const key = ["evaluation-notes", projectId, offerId ?? "requirement"];
  const { data } = useQuery({
    queryKey: key,
    queryFn: () => apiFetch<EvaluationNote[]>(offerId ? `${base}?offer_id=${encodeURIComponent(offerId)}` : base),
    refetchOnWindowFocus: true,
  });
  const notes = offerId ? data : data?.filter((n) => n.offer_id === null);
  const [body, setBody] = useState("");
  const [submission, setSubmission] = useState(token); // one token per note being written: a retry is the same note
  const [editing, setEditing] = useState<{ id: string; body: string; version: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const done = () => { setError(null); queryClient.invalidateQueries({ queryKey: key }); };
  const failed = (e: Error) => { setError(e.message); queryClient.invalidateQueries({ queryKey: key }); };
  const add = useMutation({
    mutationFn: () => apiFetch(base, { method: "POST", body: { body, offer_id: offerId ?? null, client_token: submission } }),
    onSuccess: () => { setBody(""); setSubmission(token()); done(); },
    onError: failed,
  });
  const save = useMutation({
    mutationFn: (n: { id: string; body: string; version: number }) =>
      apiFetch(`${base}/${n.id}`, { method: "PUT", body: { body: n.body }, headers: { "If-Match": String(n.version) } }),
    onSuccess: () => { setEditing(null); done(); },
    onError: failed,
  });
  const remove = useMutation({
    mutationFn: (n: EvaluationNote) => apiFetch(`${base}/${n.id}`, { method: "DELETE", headers: { "If-Match": String(n.version) } }),
    onSuccess: done,
    onError: failed,
  });
  const c = "evaluationNotes";
  return (
    <section className="border border-dashed border-border rounded px-4 py-3 mt-4 text-sm" data-testid="evaluation-notes">
      <div className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t(offerId ? `${c}.offerHeading` : `${c}.requirementHeading`)}</div>
      <p className="text-xs text-steel mb-2">{t(`${c}.private`)}</p>
      <ErrorBanner message={error} />
      <ul className="grid gap-2">
        {notes?.map((n) => (
          <li key={n.id} className="border-t border-border pt-2" data-testid="evaluation-note">
            <div className="font-mono text-[10px] text-steel">
              {n.author_name} · {n.created_at && fullDate(n.created_at, language)}
              {n.updated_at && ` · ${t(`${c}.edited`)} ${fullDate(n.updated_at, language)}`}
            </div>
            {editing?.id === n.id ? (
              <form className="grid gap-1 mt-1" onSubmit={(e) => { e.preventDefault(); save.mutate(editing); }}>
                <textarea value={editing.body} onChange={(e) => setEditing({ ...editing, body: e.target.value })} maxLength={4000} rows={3} dir="auto" className="border border-border rounded px-2 py-1 text-sm" />
                <div className="flex gap-2">
                  <button type="submit" disabled={save.isPending || !editing.body.trim()} className="bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${c}.save`)}</button>
                  <button type="button" onClick={() => setEditing(null)} className="text-xs text-steel underline">{t(`${c}.cancel`)}</button>
                </div>
              </form>
            ) : (
              <>
                <p dir="auto" className="whitespace-pre-wrap break-words">{n.body}</p>
                {n.mine && (
                  <div className="flex gap-3 mt-0.5">
                    <button type="button" onClick={() => setEditing({ id: n.id, body: n.body, version: n.version })} className="text-xs text-blue underline">{t(`${c}.edit`)}</button>
                    <button type="button" onClick={() => remove.mutate(n)} disabled={remove.isPending} className="text-xs text-red underline">{t(`${c}.remove`)}</button>
                  </div>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      <form className="mt-3 grid gap-1" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} maxLength={4000} rows={2} dir="auto" className="border border-border rounded px-2 py-1 text-sm" aria-label={t(`${c}.add`)} placeholder={t(`${c}.placeholder`)} />
        <button type="submit" disabled={add.isPending || !body.trim()} className="justify-self-start border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t(`${c}.add`)}</button>
      </form>
    </section>
  );
}
