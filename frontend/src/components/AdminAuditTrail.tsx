import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface Entry {
  id: string;
  at: string;
  action: string;
  target_type: string;
  actor: { email: string; name: string | null; role: string } | null;
  previous_value: string | null;
  new_value: string | null;
  reason: string | null;
}

// Stage 9.7: who did what, to which object, when -- the recorded trail,
// newest first, read-only. "System" is a server event (e.g. Stripe billing).
export function AdminAuditTrail({ url }: { url: string }) {
  const { t, language } = useI18n();
  const { data, error } = useQuery({ queryKey: ["admin-audit", url], queryFn: () => apiFetch<Entry[]>(url) });
  return (
    <div className="bg-white border border-border rounded px-5 py-4.5 text-sm" data-testid="admin-audit-trail">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("audit.heading")}</h3>
      {error && <p className="text-red" role="alert">{t("audit.unavailable")}</p>}
      {data && !data.length && <p className="text-steel">{t("audit.empty")}</p>}
      {!!data?.length && (
        <ol className="grid gap-1 text-xs max-h-96 overflow-y-auto">
          {data.map((e) => (
            <li key={e.id} className="border-b border-border pb-1">
              <span className="font-mono text-steel">{fullDate(e.at, language)}</span>{" "}
              <span className="font-semibold">{e.action}</span>{" "}
              <span className="text-steel">({e.target_type})</span>{" "}
              <span dir="auto">{e.actor ? `${e.actor.name ?? e.actor.email} · ${e.actor.role}` : t("audit.system")}</span>
              {(e.previous_value || e.new_value) && (
                <span className="block text-steel break-words" dir="auto">
                  {e.previous_value ? `${e.previous_value} → ` : ""}{e.new_value ?? ""}
                </span>
              )}
              {e.reason && <span className="block text-steel" dir="auto">{e.reason}</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
