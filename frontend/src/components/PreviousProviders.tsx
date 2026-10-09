import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface PreviousProvider {
  service_provider_id?: string | null;
  company_name: string | null;
  completed_transactions: number;
  last_completed_at: string | null;
  transactions: { project_id: string; title: string; completed_at: string | null }[];
}

// Stage 8.12: providers this owner organisation completed U-Tender work with --
// from completed transactions only. To work with one again, publish a new
// requirement as usual: it competes like any other.
export function PreviousProviders() {
  const { t, language } = useI18n();
  const { data } = useQuery({ queryKey: ["previous-providers"], queryFn: () => apiFetch<PreviousProvider[]>("/owner/previous-providers") });
  if (!data?.length) return null;
  return (
    <section className="mb-6 max-w-xl border border-border rounded px-4 py-3 bg-white text-ink" data-testid="previous-providers">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("previous.heading")}</h3>
      <ul className="grid gap-2">
        {data.map((p, i) => (
          <li key={i} className="text-sm">
            <span className="font-semibold" dir="auto">{p.company_name ?? t("owner.projectDetail.theServiceProvider")}</span>
            {" · "}
            {t("previous.together").replace("{n}", String(p.completed_transactions))}
            {p.last_completed_at && ` · ${t("previous.last")} ${fullDate(p.last_completed_at, language)}`}
            <div className="text-xs text-steel">
              {p.transactions.map((tx, j) => (
                <span key={tx.project_id}>
                  {j > 0 && ", "}
                  <Link to={`/owner/projects/${tx.project_id}`} className="text-blue underline" dir="auto">{tx.title}</Link>
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-steel mt-2">{t("previous.note")}</p>
    </section>
  );
}

// Batch C: repeat business -- on an open requirement, the owner invites a
// provider it completed work with. A notice only: the requirement's
// eligibility rules apply, and the offer competes like any other.
export function InvitePreviousProviders({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const { data } = useQuery({ queryKey: ["previous-providers"], queryFn: () => apiFetch<PreviousProvider[]>("/owner/previous-providers") });
  const [invited, setInvited] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const invite = useMutation({
    mutationFn: (providerId: string) => apiFetch(`/owner/projects/${projectId}/invitations/${providerId}`, { method: "POST" }),
    onSuccess: (_, providerId) => {
      setError(null);
      setInvited((prev) => [...prev, providerId]);
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("previous.inviteError")),
  });
  const providers = (data ?? []).filter((p) => p.service_provider_id);
  if (!providers.length) return null;
  return (
    <section className="mb-6 max-w-xl border border-border rounded px-4 py-3 bg-white text-ink" data-testid="invite-previous">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("previous.inviteHeading")}</h3>
      {error && <p className="text-xs text-red mb-2">{error}</p>}
      <ul className="grid gap-2">
        {providers.map((p) => (
          <li key={p.service_provider_id} className="flex items-center gap-3 text-sm">
            <span className="flex-1 font-semibold" dir="auto">{p.company_name ?? t("owner.projectDetail.theServiceProvider")}</span>
            {invited.includes(p.service_provider_id!) ? (
              <span className="font-mono text-[11px] text-green">{t("previous.invited")}</span>
            ) : (
              <button type="button" onClick={() => invite.mutate(p.service_provider_id!)} disabled={invite.isPending} className="text-xs text-blue underline disabled:opacity-60">
                {t("previous.invite")}
              </button>
            )}
          </li>
        ))}
      </ul>
      <p className="text-[11px] text-steel mt-2">{t("previous.inviteNote")}</p>
    </section>
  );
}
