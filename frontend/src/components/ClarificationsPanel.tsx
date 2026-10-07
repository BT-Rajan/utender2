import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { Clarification, ClarificationAttachment } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";
import { formatDeadline, formatSize } from "@/lib/format";

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
  // Stage 4.7 follow-up: files for the question being asked, and for each answer.
  const [questionFiles, setQuestionFiles] = useState<File[]>([]);
  const [answerFiles, setAnswerFiles] = useState<Record<string, File[]>>({});
  const upload = (clarificationId: string, files: File[]) => {
    if (!files.length) return Promise.resolve();
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return apiFetch(`/projects/${projectId}/clarifications/${clarificationId}/attachments`, { method: "POST", formData: form });
  };
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
    mutationFn: async () => {
      const asked = await apiFetch<Clarification>(`/projects/${projectId}/clarifications`, {
        method: "POST",
        body: { question, shared_with_all: sharedWithAll },
      });
      await upload(asked.id, questionFiles);
    },
    onSuccess: () => {
      setQuestion("");
      setQuestionFiles([]);
      invalidate();
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("clarifications.askError")),
  });

  const answerMutation = useMutation({
    // The answer's files go first, so they are there when providers are told.
    mutationFn: async (clarificationId: string) => {
      await upload(clarificationId, answerFiles[clarificationId] ?? []);
      return apiFetch(`/projects/${projectId}/clarifications/${clarificationId}/answer`, {
        method: "POST",
        body: { answer: drafts[clarificationId] || "", shared_with_all: publish[clarificationId] ? true : null },
      });
    },
    onSuccess: (_, clarificationId) => {
      setDrafts((d) => ({ ...d, [clarificationId]: "" }));
      setAnswerFiles((f) => ({ ...f, [clarificationId]: [] }));
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
              <AttachmentLinks files={c.attachments?.filter((a) => a.part === "question")} />
              {c.answer ? (
                <div className="mt-1.5 ps-3 border-s-2 border-blue">
                  <p dir="auto" className="text-[12.5px] text-steel whitespace-pre-wrap break-words">{c.answer}</p>
                  <AttachmentLinks files={c.attachments?.filter((a) => a.part === "answer")} />
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
                  <FilePicker id={`answer-files-${c.id}`} files={answerFiles[c.id] ?? []} onChange={(files) => setAnswerFiles((f) => ({ ...f, [c.id]: files }))} />
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
          <div className="mb-2">
            <FilePicker id="question-files" files={questionFiles} onChange={setQuestionFiles} />
          </div>
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

// Files on a question or an answer, through their signed, named links.
function AttachmentLinks({ files }: { files?: ClarificationAttachment[] }) {
  if (!files?.length) return null;
  return (
    <ul className="flex flex-wrap gap-2 mt-1" data-testid="clarification-files">
      {files.map((a) => (
        <li key={a.id}>
          <a href={a.url} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-blue underline bg-blue-tint px-2 py-1 rounded">
            {a.file_name} · {formatSize(a.size_bytes)}
          </a>
        </li>
      ))}
    </ul>
  );
}

// Up to five files: PDF, images, drawings (.dwg), Excel, Word.
function FilePicker({ id, files, onChange }: { id: string; files: File[]; onChange: (files: File[]) => void }) {
  const { t } = useI18n();
  return (
    <div className="text-[11.5px] text-steel">
      <label htmlFor={id} className="block mb-0.5">{t("clarifications.attachFiles")}</label>
      <input
        id={id}
        type="file"
        multiple
        accept=".pdf,.dwg,.xlsx,.docx,.jpg,.jpeg,.png"
        onChange={(e) => onChange(Array.from(e.target.files ?? []).slice(0, 5))}
        className="text-xs"
      />
      {files.length > 0 && <span className="block">{files.map((f) => f.name).join(", ")}</span>}
    </div>
  );
}
