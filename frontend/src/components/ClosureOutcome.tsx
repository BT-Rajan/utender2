import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ClosureReason, ProjectDetail, ProjectStatus } from "@/api/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";

type T = (key: string) => string;

// Stage 3.16: a short label for where a requirement stands, telling apart the
// ways it can end without a U-Tender award.
export function outcomeLabel(t: T, status: ProjectStatus, reason?: ClosureReason | null): string {
  if (status === "no_award") return reason === "closed_externally" ? t("closure.labelExternal") : t("closure.labelNoSuitable");
  if (status === "canceled") return t("closure.labelCanceled");
  if (status === "expired") return t("closure.labelExpired");
  return status.replace(/_/g, " ");
}

// Stage 6.16: a provider's own offer, as its status reads once the requirement
// has an outcome. An offer still "submitted" on a requirement that ended
// without an award (no suitable offer, outside U-Tender, cancelled, expired)
// is shown with that outcome -- never as an offer still in play.
export function offerStatusLabel(t: T, offerStatus: string, projectStatus: ProjectStatus, reason?: ClosureReason | null): string {
  if (offerStatus === "submitted") {
    if (projectStatus === "no_award" || projectStatus === "canceled" || projectStatus === "expired") return outcomeLabel(t, projectStatus, reason);
    return t("service_provider.feed.bidPlaced");
  }
  return t(`feed.offer_${offerStatus}`);
}

// The fuller sentence shown on the requirement itself, to owner and providers alike.
export function outcomeText(t: T, status: ProjectStatus, reason?: ClosureReason | null): string | null {
  if (status === "no_award") return reason === "closed_externally" ? t("closure.textExternal") : t("closure.textNoSuitable");
  if (status === "canceled") return `${t("closure.textCanceled")} ${t(`closure.reason_${reason ?? "other"}`)}`;
  if (status === "expired") return t("closure.textExpired");
  return null;
}

export function ClosureOutcome({ project }: { project: Pick<ProjectDetail, "status" | "closure_reason" | "closure_note"> }) {
  const { t } = useI18n();
  const text = outcomeText(t, project.status, project.closure_reason);
  if (!text) return null;
  return (
    <div className="border border-border bg-border/30 rounded px-4 py-3 mb-6 text-sm text-steel max-w-2xl" data-testid="closure-outcome">
      <strong className="font-display text-navy block">{outcomeLabel(t, project.status, project.closure_reason)}</strong>
      {text}
      <p className="text-xs text-steel-light mt-1">{t("closure.offersKept")}</p>
      {project.closure_note && (
        <p className="text-xs text-steel mt-2" data-testid="closure-note">
          <span className="font-semibold">{t("closure.yourNote")}</span> {project.closure_note}
        </p>
      )}
    </div>
  );
}

const CANCEL_REASONS: ClosureReason[] = ["not_needed", "postponed", "other"];

// The owner's ways of ending a published requirement without a U-Tender award.
export function EndRequirement({ project }: { project: ProjectDetail }) {
  const { t } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<ClosureReason>("not_needed");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: (action: "cancel" | "close-externally" | "no-award") =>
      apiFetch(`/owner/projects/${project.id}/${action}`, {
        method: "POST",
        body: { reason: action === "cancel" ? reason : undefined, note: note.trim() || undefined },
      }),
    onSuccess: () => {
      setError(null);
      setOpen(false);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("closure.error")),
    // Stage 6.17: either way, show the requirement and its offers as the
    // server now holds them -- e.g. refused because a colleague already decided.
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
      queryClient.invalidateQueries({ queryKey: ["owner-offers", project.id] });
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
    },
  });
  const decided = project.status === "closed" || project.status === "under_evaluation";

  function run(action: "cancel" | "close-externally" | "no-award", title: string, body: string, label: string) {
    void confirm({ title, body, confirmLabel: label, tone: "danger" }).then((ok) => ok && act.mutate(action));
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-xs text-red underline mb-6">
        {t("closure.open")}
      </button>
    );
  }
  return (
    <div className="border border-border rounded px-4 py-3 bg-white grid gap-3 mb-6 max-w-2xl text-sm">
      <strong className="font-display text-navy">{t("closure.heading")}</strong>
      <p className="text-xs text-steel-light">{t("closure.hint")}</p>
      <label htmlFor="closure-note" className="text-navy">{t("closure.note")}</label>
      <textarea id="closure-note" maxLength={1000} rows={2} value={note} onChange={(e) => setNote(e.target.value)} className="border border-border rounded px-3 py-2 text-sm" />
      <p className="text-xs text-steel-light -mt-2">{t("closure.noteHint")}</p>

      <fieldset className="border-t border-border pt-3 grid gap-1">
        <legend className="text-navy font-semibold">{t("closure.cancelHeading")}</legend>
        {CANCEL_REASONS.map((r) => (
          <label key={r} className="flex gap-2 items-center">
            <input type="radio" name="cancel-reason" value={r} checked={reason === r} onChange={() => setReason(r)} />
            {t(`closure.reason_${r}`)}
          </label>
        ))}
        <button
          type="button"
          disabled={act.isPending}
          onClick={() => run("cancel", t("closure.cancelConfirm"), t("closure.cancelConfirmBody"), t("closure.cancel"))}
          className="mt-1 w-fit bg-red-tint text-red text-xs font-semibold rounded px-4 py-2"
        >
          {t("closure.cancel")}
        </button>
      </fieldset>

      <div className="border-t border-border pt-3 grid gap-1">
        <span className="text-navy font-semibold">{t("closure.externalHeading")}</span>
        <p className="text-xs text-steel-light">{t("closure.externalHint")}</p>
        <button
          type="button"
          disabled={act.isPending}
          onClick={() => run("close-externally", t("closure.externalConfirm"), t("closure.externalConfirmBody"), t("closure.external"))}
          className="w-fit border border-navy text-navy text-xs font-semibold rounded px-4 py-2"
        >
          {t("closure.external")}
        </button>
      </div>

      {decided && (
        <div className="border-t border-border pt-3 grid gap-1">
          <span className="text-navy font-semibold">{t("closure.noSuitableHeading")}</span>
          <p className="text-xs text-steel-light">{t("closure.noSuitableHint")}</p>
          <button
            type="button"
            disabled={act.isPending}
            onClick={() => run("no-award", t("closure.noSuitableConfirm"), t("closure.noSuitableConfirmBody"), t("closure.noSuitable"))}
            className="w-fit border border-navy text-navy text-xs font-semibold rounded px-4 py-2"
          >
            {t("closure.noSuitable")}
          </button>
        </div>
      )}

      <ErrorBanner message={error} />
      <button type="button" onClick={() => setOpen(false)} className="w-fit border border-border text-steel text-xs font-semibold rounded px-4 py-2">
        {t("closure.dismiss")}
      </button>
    </div>
  );
}

// An ended requirement stays ended; when the work comes back, the owner starts
// a new draft from its content (the server copies it; the old one is untouched).
// Stage 8.11: likewise from a completed one, when the same need comes back.
export function StartAgain({ project, similar = false }: { project: ProjectDetail; similar?: boolean }) {
  const { t } = useI18n();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const token = useRef(typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`);
  const act = useMutation({
    mutationFn: () => apiFetch<ProjectDetail>(`/owner/projects/${project.id}/restart`, { method: "POST", body: { creation_token: token.current } }),
    onSuccess: (draft) => {
      queryClient.invalidateQueries({ queryKey: ["owner-projects"] });
      navigate(`/owner/projects/${draft.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("closure.error")),
  });
  return (
    <div className="mb-6 max-w-2xl">
      <ErrorBanner message={error} />
      <button
        type="button"
        disabled={act.isPending}
        onClick={() =>
          void confirm(
            similar
              ? { title: t("closure.similarConfirm"), body: t("closure.similarConfirmBody"), confirmLabel: t("closure.similar") }
              : { title: t("closure.restartConfirm"), body: t("closure.restartConfirmBody"), confirmLabel: t("closure.restart") },
          ).then((ok) => ok && act.mutate())
        }
        className="border border-navy text-navy hover:bg-navy hover:text-white disabled:opacity-60 text-xs font-semibold rounded px-4 py-2"
        data-testid={similar ? "create-similar" : undefined}
      >
        {similar ? t("closure.similar") : t("closure.restart")}
      </button>
    </div>
  );
}
