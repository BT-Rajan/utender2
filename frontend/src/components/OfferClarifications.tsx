import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { OfferClarification } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

// Stage 6.10: clarifying one submitted offer during evaluation -- the owner's
// side asks, that offer's provider side answers. Private to the two. An
// answer sits beside the offer and never changes it.
export function OfferClarifications({
  projectId,
  offerId,
  role,
  canAsk = false,
}: {
  projectId: string;
  offerId?: string; // the owner's view: which offer
  role: "owner" | "provider";
  canAsk?: boolean;
}) {
  const { t, language } = useI18n();
  const queryClient = useQueryClient();
  const base = role === "owner" ? `/owner/projects/${projectId}/offers/${offerId}/clarifications` : `/projects/${projectId}/offers/mine/clarifications`;
  const key = ["offer-clarifications", role, projectId, offerId ?? "mine"];
  const { data: items } = useQuery({ queryKey: key, queryFn: () => apiFetch<OfferClarification[]>(base), refetchInterval: 60 * 1000, refetchOnWindowFocus: true });
  const [text, setText] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });
  const ask = useMutation({
    mutationFn: () => apiFetch(base, { method: "POST", body: { question: text } }),
    onSuccess: () => { setText(""); setError(null); refresh(); },
    onError: (e: Error) => { setError(e.message); refresh(); },
  });
  const answer = useMutation({
    mutationFn: (id: string) => apiFetch(`${base}/${id}/answer`, { method: "POST", body: { answer: answers[id] ?? "" } }),
    onSuccess: () => { setError(null); refresh(); },
    onError: (e: Error) => { setError(e.message); refresh(); },
  });
  if (!items?.length && !canAsk) return null;
  const c = "offerClarification";
  return (
    <section className="border border-border rounded px-4 py-3 mt-4 text-sm" data-testid="offer-clarifications">
      <div className="font-mono text-[11px] uppercase tracking-wide text-navy mb-1">{t(`${c}.heading`)}</div>
      <p className="text-xs text-steel mb-2">{t(role === "owner" ? `${c}.ownerNote` : `${c}.providerNote`)}</p>
      {error && <ErrorBanner message={error} />}
      <ol className="grid gap-3">
        {items?.map((q) => (
          <li key={q.id} className="border-t border-border pt-2" data-testid="offer-clarification">
            <div className="font-mono text-[10px] text-steel">
              {t(`${c}.asked`)} {q.asked_at && fullDate(q.asked_at, language)}
              {q.asked_by_name && ` · ${q.asked_by_name}`}
              {q.offer_revision != null && ` · ${t("ownerOffer.revision").replace("{n}", String(q.offer_revision))}`}
            </div>
            <p dir="auto" className="whitespace-pre-wrap break-words">{q.question}</p>
            {q.answer != null ? (
              <div className="mt-1 ps-3 border-s-2 border-blue">
                <div className="font-mono text-[10px] text-steel">
                  {t(`${c}.answered`)} {q.answered_at && fullDate(q.answered_at, language)}
                  {q.answered_by_name && ` · ${q.answered_by_name}`}
                </div>
                <p dir="auto" className="whitespace-pre-wrap break-words">{q.answer}</p>
              </div>
            ) : role === "provider" ? (
              <form
                className="mt-1 grid gap-1"
                onSubmit={(e) => { e.preventDefault(); answer.mutate(q.id); }}
              >
                <textarea
                  value={answers[q.id] ?? ""}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))}
                  maxLength={4000}
                  rows={3}
                  dir="auto"
                  className="border border-border rounded px-2 py-1 text-sm"
                  aria-label={t(`${c}.answer`)}
                />
                <button type="submit" disabled={answer.isPending || !(answers[q.id] ?? "").trim()} className="justify-self-start bg-navy text-white text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">
                  {t(`${c}.sendAnswer`)}
                </button>
              </form>
            ) : (
              <p className="text-xs text-steel-light mt-1">{t(`${c}.waiting`)}</p>
            )}
          </li>
        ))}
      </ol>
      {canAsk && role === "owner" && (
        <form className="mt-3 grid gap-1" onSubmit={(e) => { e.preventDefault(); ask.mutate(); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} rows={3} dir="auto" className="border border-border rounded px-2 py-1 text-sm" aria-label={t(`${c}.ask`)} placeholder={t(`${c}.askPlaceholder`)} />
          <button type="submit" disabled={ask.isPending || !text.trim()} className="justify-self-start border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">
            {t(`${c}.ask`)}
          </button>
        </form>
      )}
    </section>
  );
}
