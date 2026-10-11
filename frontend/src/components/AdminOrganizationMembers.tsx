import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, apiFetch } from "@/api/client";
import { useConfirm } from "@/components/ConfirmDialog";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

export interface Member {
  user_id: string;
  full_name: string | null;
  email: string;
  role: "admin" | "member";
  position: string | null;
  joined_at: string;
  deactivated_at: string | null;
}

// Stage 9.2: an organisation's people, for an admin -- and, for one person
// (a lost device, someone who left), deactivating their account without
// suspending the organisation. Reactivating restores exactly what they had.
export function AdminOrganizationMembers({ members, queryKey, organizationId }: { members: Member[]; queryKey: unknown[]; organizationId?: string | null }) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (v: { id: string; to: "deactivate" | "reactivate" }) => apiFetch(`/admin/users/${v.id}/${v.to}`, { method: "POST", body: {} }),
    onSuccess: () => { setError(null); queryClient.invalidateQueries({ queryKey }); },
    onError: (e: Error) => { setError(e instanceof ApiError ? e.message : t("members.error")); queryClient.invalidateQueries({ queryKey }); },
  });
  const appoint = useMutation({
    mutationFn: (userId: string) => apiFetch(`/admin/organizations/${organizationId}/representative`, { method: "POST", body: { user_id: userId } }),
    onSuccess: () => { setError(null); queryClient.invalidateQueries({ queryKey }); },
    onError: (e: Error) => { setError(e instanceof ApiError ? e.message : t("members.error")); queryClient.invalidateQueries({ queryKey }); },
  });
  if (!members.length) return null;
  return (
    <div className="mt-4" data-testid="organization-members">
      <h4 className="font-mono text-[10.5px] uppercase tracking-wide text-steel mb-2">{t("members.heading")}</h4>
      <ErrorBanner message={error} />
      <ul className="grid gap-2 text-sm">
        {members.map((m) => (
          <li key={m.user_id} className="flex items-center justify-between gap-3 flex-wrap">
            <span dir="auto">
              <span className="font-semibold">{m.full_name ?? m.email}</span>
              <span className="text-steel"> · {m.email} · {t(m.role === "admin" ? "members.representative" : "members.member")}{m.position ? ` · ${m.position}` : ""}</span>
              {m.deactivated_at && <span className="text-red"> · {t("members.deactivatedOn")} {fullDate(m.deactivated_at, language)}</span>}
            </span>
            {organizationId && m.role !== "admin" && !m.deactivated_at && (
              <button
                type="button"
                disabled={appoint.isPending}
                onClick={() => {
                  void confirm({
                    title: t("members.makeRepresentativeTitle"),
                    body: t("members.makeRepresentativeBody"),
                    confirmLabel: t("members.makeRepresentative"),
                  }).then((ok) => ok && appoint.mutate(m.user_id));
                }}
                className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1 disabled:opacity-60"
              >
                {t("members.makeRepresentative")}
              </button>
            )}
            <button
              type="button"
              disabled={change.isPending}
              onClick={() => {
                const to = m.deactivated_at ? "reactivate" : "deactivate";
                void confirm({
                  title: t(to === "deactivate" ? "members.deactivateTitle" : "members.reactivateTitle"),
                  body: t(to === "deactivate" ? "members.deactivateBody" : "members.reactivateBody"),
                  confirmLabel: t(to === "deactivate" ? "members.deactivate" : "members.reactivate"),
                }).then((ok) => ok && change.mutate({ id: m.user_id, to }));
              }}
              className={`border text-xs font-semibold rounded px-3 py-1 disabled:opacity-60 ${m.deactivated_at ? "border-navy text-navy" : "border-red text-red"}`}
            >
              {t(m.deactivated_at ? "members.reactivate" : "members.deactivate")}
            </button>
          </li>
        ))}
      </ul>
      {organizationId && <AddPerson organizationId={organizationId} queryKey={queryKey} />}
    </div>
  );
}

// Put a person on the organization -- the way back for one whose representative
// can no longer act. The person must already have an account (verified email).
function AddPerson({ organizationId, queryKey }: { organizationId: string; queryKey: unknown[] }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [state, setState] = useState<{ pending: boolean; error: string | null; done: boolean }>({ pending: false, error: null, done: false });

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    setState({ pending: true, error: null, done: false });
    try {
      await apiFetch(`/admin/organizations/${organizationId}/members`, {
        method: "POST",
        body: {
          email: String(data.get("email") ?? "").trim(),
          position: String(data.get("position") ?? "").trim() || null,
          representative: data.get("representative") === "on",
          reason: String(data.get("reason") ?? "").trim() || null,
        },
      });
      form.reset();
      setState({ pending: false, error: null, done: true });
      await queryClient.invalidateQueries({ queryKey });
    } catch (err) {
      setState({ pending: false, error: err instanceof ApiError ? err.message : t("members.error"), done: false });
    }
  }

  const input = "border border-border rounded px-3 py-1.5 text-sm w-full";
  return (
    <form onSubmit={submit} className="mt-4 grid gap-2 max-w-md" data-testid="add-organization-person">
      <h4 className="font-mono text-[10.5px] uppercase tracking-wide text-steel">{t("members.addHeading")}</h4>
      <input name="email" type="email" required placeholder={t("members.addEmail")} aria-label={t("members.addEmail")} className={input} dir="ltr" />
      <input name="position" maxLength={150} placeholder={t("members.addPosition")} aria-label={t("members.addPosition")} className={input} dir="auto" />
      <input name="reason" maxLength={500} placeholder={t("members.addReason")} aria-label={t("members.addReason")} className={input} dir="auto" />
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" name="representative" />{t("members.addAsRepresentative")}</label>
      {state.error && <p role="alert" className="text-red text-xs">{state.error}</p>}
      {state.done && <p className="text-green text-xs">{t("members.added")}</p>}
      <button type="submit" disabled={state.pending} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 w-fit disabled:opacity-60">
        {state.pending ? t("members.adding") : t("members.addSubmit")}
      </button>
    </form>
  );
}
