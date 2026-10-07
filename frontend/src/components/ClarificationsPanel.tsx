import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { Clarification } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";
import { formatDeadline } from "@/lib/format";

export function ClarificationsPanel({
  projectId,
  role,
  canAsk = true,
  qaOpen = true,
  closesAt = null,
}: {
  projectId: string;
  role: "owner" | "service_provider";
  canAsk?: boolean;
  // Stage 3.10: the Q&A closes for both sides at the question cut-off.
  qaOpen?: boolean;
  closesAt?: string | null;
}) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState("");
  const [sharedWithAll, setSharedWithAll] = useState(true);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [publish, setPublish] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  const { data: clarifications } = useQuery({
    queryKey: ["clarifications", projectId],
    queryFn: () => apiFetch<Clarification[]>(`/projects/${projectId}/clarifications`),
  });

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["clarifications", projectId] });
  };

  const askMutation = useMutation({
    mutationFn: () =>
      apiFetch(`/projects/${projectId}/clarifications`, {
        method: "POST",
        body: { question, shared_with_all: sharedWithAll },
      }),
    onSuccess: () => {
      setQuestion("");
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("clarifications.askError")),
  });

  const answerMutation = useMutation({
    mutationFn: (clarificationId: string) =>
      apiFetch(`/projects/${projectId}/clarifications/${clarificationId}/answer`, {
        method: "POST",
        body: { answer: drafts[clarificationId] || "", shared_with_all: publish[clarificationId] ? true : null },
      }),
    onSuccess: (_, clarificationId) => {
      setDrafts((d) => ({ ...d, [clarificationId]: "" }));
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("clarifications.answerError")),
  });

  return (
    <div className="bg-white border border-border rounded px-5 py-4.5">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-3">{t("clarifications.heading")}</h3>

      {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2 mb-3">{error}</p>}

      {closesAt && (
        <p className={`text-[11.5px] mb-2 ${qaOpen ? "text-steel" : "text-amber-dark"}`}>
          {(qaOpen ? t("clarifications.closesAt") : t("clarifications.closedAt")).replace("{date}", formatDeadline(closesAt))}
        </p>
      )}
      {!clarifications?.length ? (
        <p className="text-[12.5px] text-steel-light mb-3">{t("clarifications.noQuestions")}</p>
      ) : (
        <ul className="space-y-3 mb-4">
          {clarifications.map((c) => (
            <li key={c.id} className="border-b border-border pb-3 last:border-0">
              <div className="flex items-center gap-2 mb-1">
                {role === "owner" &&
                  (c.service_provider_company_name ? (
                    <span className="font-mono text-[10px] text-steel-light">{c.service_provider_company_name}</span>
                  ) : (
                    <span className="font-mono text-[10px] text-steel-light italic">{t("clarifications.sealedBidder")}</span>
                  ))}
                {c.mine && <span className="font-mono text-[9px] uppercase text-blue">{t("clarifications.yourQuestion")}</span>}
                {!c.shared_with_all && <span className="font-mono text-[9px] uppercase text-amber-dark">{t("clarifications.privateTag")}</span>}
                <span className="font-mono text-[10px] text-steel-light">{formatDeadline(c.created_at)}</span>
              </div>
              <p dir="auto" className="text-[13px] text-navy whitespace-pre-wrap break-words">{c.question}</p>
              {c.answer ? (
                <div className="mt-1.5 ps-3 border-s-2 border-blue">
                  <p dir="auto" className="text-[12.5px] text-steel whitespace-pre-wrap break-words">{c.answer}</p>
                  <p className="font-mono text-[10px] text-steel-light mt-0.5">
                    {t("clarifications.answeredOn").replace("{date}", c.answered_at ? formatDeadline(c.answered_at) : "")}
                    {c.answered_by_name && ` · ${c.answered_by_name}`}
                  </p>
                  {/* Stage 4.7: an answer that changed the requirement points at the change itself. */}
                  {c.amendment_number && (
                    <p className="text-[11.5px] text-amber-dark mt-0.5" data-testid="clarification-amendment">
                      {t("clarifications.cameWithChange").replace("{n}", String(c.amendment_number))}
                    </p>
                  )}
                </div>
              ) : role === "owner" && !qaOpen ? (
                <p className="text-[12px] text-steel-light mt-1 italic">{t("clarifications.unansweredClosed")}</p>
              ) : role === "owner" ? (
                <div className="mt-2 grid gap-1.5">
                  <textarea
                    value={drafts[c.id] || ""}
                    onChange={(e) => setDrafts((d) => ({ ...d, [c.id]: e.target.value }))}
                    placeholder={t("clarifications.writeAnswerPlaceholder")}
                    rows={2}
                    maxLength={4000}
                    className="border border-border rounded px-2.5 py-1.5 text-xs"
                  />
                  {!c.shared_with_all && (
                    <label className="flex items-center gap-1.5 text-[11.5px] text-steel">
                      <input type="checkbox" checked={!!publish[c.id]} onChange={(e) => setPublish((p) => ({ ...p, [c.id]: e.target.checked }))} />
                      {t("clarifications.publishForAll")}
                    </label>
                  )}
                  <p className="text-[11px] text-steel-light">{t("clarifications.materialHint")}</p>
                  <button
                    type="button"
                    onClick={() => answerMutation.mutate(c.id)}
                    disabled={answerMutation.isPending || !drafts[c.id]?.trim()}
                    className="w-fit bg-navy hover:bg-navy-deep disabled:opacity-40 text-white text-xs font-semibold rounded px-3 py-1.5"
                  >
                    {t("clarifications.answerButton")}
                  </button>
                </div>
              ) : (
                <p className="text-[12px] text-steel-light mt-1 italic">{t("clarifications.awaitingAnswer")}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {role === "service_provider" && canAsk && (
        <div className="border-t border-border pt-3">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            maxLength={2000}
            placeholder={t("clarifications.askPlaceholder")}
            className="w-full border border-border rounded px-3 py-2 text-sm resize-y mb-2"
          />
          <div className="flex items-center justify-between gap-2">
            <label className="flex items-center gap-1.5 text-[11.5px] text-steel">
              <input type="checkbox" checked={sharedWithAll} onChange={(e) => setSharedWithAll(e.target.checked)} />
              {t("clarifications.shareCheckboxLabel")}
            </label>
            <button
              type="button"
              onClick={() => askMutation.mutate()}
              disabled={askMutation.isPending || !question.trim()}
              className="bg-amber hover:bg-amber-dark disabled:opacity-40 text-white text-xs font-semibold rounded px-4 py-2"
            >
              {t("clarifications.askButton")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
