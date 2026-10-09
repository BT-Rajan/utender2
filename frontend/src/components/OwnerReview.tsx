import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiFetch } from "@/api/client";
import { useConfirm } from "@/components/ConfirmDialog";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ReceivedReview, ReviewResponse } from "@/components/ReceivedReview";
import { RatingInput } from "@/components/RatingInput";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface ReviewRecord {
  id: string;
  rating: number;
  comment: string | null;
  created_at: string;
  response?: string | null;
  response_at?: string | null;
  hidden?: boolean;
  revealed?: boolean; // Batch C: sealed from the owner until both reviewed, or reveals_on
  reveals_on?: string | null;
}

// Stage 8.4: the winning provider reviews the owner -- once the transaction is
// completed, once per transaction. Its own review is shown once recorded, and
// the owner's review of it once the owner has written one (Stage 8.6).
export function OwnerReview({ projectId }: { projectId: string }) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const { data: transaction } = useQuery({
    queryKey: ["agreement", projectId],
    queryFn: () => apiFetch<{ status: string; owner_name: string | null }>(`/projects/${projectId}/agreement`),
    retry: false,
  });
  const completed = transaction?.status === "completed";
  const key = ["provider-review", projectId];
  const { data: review } = useQuery({
    queryKey: key,
    queryFn: () => apiFetch<ReviewRecord | null>(`/service-provider/projects/${projectId}/review`),
    enabled: completed,
  });
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = useMutation({
    mutationFn: () => apiFetch<ReviewRecord>("/service-provider/reviews", { method: "POST", body: { project_id: projectId, rating, comment: comment || null } }),
    onSuccess: (saved) => { setError(null); queryClient.setQueryData(key, saved); },
    onError: (e: Error) => { setError(e instanceof ApiError ? e.message : t("ownerReview.error")); queryClient.invalidateQueries({ queryKey: key }); },
  });
  if (!completed) return null;
  const name = transaction?.owner_name ?? t("ownerReview.theOwner");

  return (
    <section className="mt-4 max-w-xl text-ink" data-testid="owner-review">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2" dir="auto">{t("ownerReview.heading").replace("{owner}", name)}</h3>
      <ErrorBanner message={error} />
      {review ? (
        <div className="bg-white border border-border rounded px-4 py-3">
          <span className="text-amber text-lg tracking-tight" aria-label={t("ownerReview.rating").replace("{n}", String(review.rating))}>
            {"★".repeat(review.rating)}{"☆".repeat(5 - review.rating)}
          </span>
          {review.comment && <p className="text-sm text-steel mt-1 whitespace-pre-wrap break-words" dir="auto">{review.comment}</p>}
          <div className="font-mono text-[10px] text-steel mt-1">{t("ownerReview.submitted")} {fullDate(review.created_at, language)}</div>
          {review.hidden && <p className="text-xs text-amber-dark mt-1">{t("report.hiddenNote")}</p>}
          {review.revealed === false && (
            <p className="text-xs text-steel mt-1" data-testid="review-sealed">
              {t("review.sealed").replace("{date}", review.reveals_on ? fullDate(review.reveals_on, language, false) : "")}
            </p>
          )}
          <ReviewResponse response={review.response} at={review.response_at} label={t("review.theirResponse")} reportBase={`/service-provider/projects/${projectId}`} />
        </div>
      ) : (
        <form
          className="bg-white border border-border rounded px-4 py-3 grid gap-3"
          onSubmit={(ev) => {
            ev.preventDefault();
            void confirm({ title: t("review.confirmTitle"), body: t("ownerReview.confirmBody"), confirmLabel: t("ownerReview.submit") }).then((ok) => ok && submit.mutate());
          }}
        >
          <RatingInput value={rating} onChange={setRating} />
          <textarea
            value={comment}
            onChange={(ev) => setComment(ev.target.value)}
            rows={3}
            maxLength={2000}
            dir="auto"
            aria-label={t("ownerReview.comment")}
            placeholder={t("ownerReview.comment")}
            className="w-full border border-border rounded px-3 py-2 text-sm"
          />
          <button type="submit" disabled={!rating || submit.isPending} className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2 w-fit">
            {t("ownerReview.submit")}
          </button>
        </form>
      )}
      <ReceivedReview url={`/service-provider/projects/${projectId}/review/received`} from={name} />
    </section>
  );
}
