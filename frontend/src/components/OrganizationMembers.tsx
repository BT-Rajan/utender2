import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";

interface Member {
  user_id: string;
  full_name: string | null;
  email: string;
  role: "admin" | "member";
  position: string | null;
}

// Everything done for an organization is shared by its members: they act as
// the organization (its verification, requirements, offers and questions).
// The authorized representative adds colleagues who already have an account.
export function OrganizationMembers() {
  const { t } = useI18n();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [position, setPosition] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data: members } = useQuery({
    queryKey: ["organization-members"],
    queryFn: () => apiFetch<Member[]>("/account/organization/members"),
  });
  const done = (data: Member[]) => {
    setError(null);
    queryClient.setQueryData(["organization-members"], data);
  };
  const fail = (err: unknown) => setError(err instanceof ApiError ? err.detail : t("organization.error"));
  const add = useMutation({
    mutationFn: () => apiFetch<Member[]>("/account/organization/members", { method: "POST", body: { email, position: position || null } }),
    onSuccess: (data) => {
      setEmail("");
      setPosition("");
      done(data);
    },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiFetch<Member[]>(`/account/organization/members/${id}`, { method: "DELETE" }),
    onSuccess: done,
    onError: fail,
  });

  if (!members) return null;
  const isRepresentative = members.some((m) => m.user_id === user?.id && m.role === "admin");
  return (
    <section className="bg-white border border-border rounded px-5 py-4.5 mb-8 max-w-xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("organization.heading")}</h2>
      <p className="text-[13px] text-steel mb-3">{t("organization.hint")}</p>
      <ErrorBanner message={error} />
      <ul className="divide-y divide-border mb-3">
        {members.map((m) => (
          <li key={m.user_id} className="py-2 flex items-center gap-3 text-sm">
            <span className="flex-1">
              <span className="text-navy">{m.full_name || m.email}</span>
              <span className="block text-xs text-steel-light">
                {m.email}
                {m.position && ` · ${m.position}`} · {t(m.role === "admin" ? "organization.representative" : "organization.member")}
              </span>
            </span>
            {isRepresentative && m.role !== "admin" && (
              <button
                type="button"
                onClick={() => {
                  if (window.confirm(t("organization.removeConfirm"))) remove.mutate(m.user_id);
                }}
                className="text-xs text-red underline"
              >
                {t("organization.remove")}
              </button>
            )}
          </li>
        ))}
      </ul>
      {isRepresentative && (
        <form
          className="grid sm:grid-cols-[1fr_10rem_auto] gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate();
          }}
        >
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t("organization.emailPlaceholder")}
            aria-label={t("organization.email")}
            className="border border-border rounded px-3 py-2 text-sm"
          />
          <input
            value={position}
            onChange={(e) => setPosition(e.target.value)}
            placeholder={t("organization.position")}
            aria-label={t("organization.position")}
            maxLength={150}
            className="border border-border rounded px-3 py-2 text-sm"
          />
          <button type="submit" disabled={add.isPending} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-4 py-2">
            {t("organization.add")}
          </button>
          <p className="sm:col-span-3 text-xs text-steel-light">{t("organization.addHint")}</p>
        </form>
      )}
    </section>
  );
}
