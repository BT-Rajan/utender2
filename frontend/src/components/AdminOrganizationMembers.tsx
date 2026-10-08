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
export function AdminOrganizationMembers({ members, queryKey }: { members: Member[]; queryKey: unknown[] }) {
  const { t, language } = useI18n();
  const confirm = useConfirm();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (v: { id: string; to: "deactivate" | "reactivate" }) => apiFetch(`/admin/users/${v.id}/${v.to}`, { method: "POST", body: {} }),
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
    </div>
  );
}
