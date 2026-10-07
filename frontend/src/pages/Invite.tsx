import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { ErrorBanner } from "@/components/ErrorBanner";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { useI18n } from "@/i18n/I18nContext";
import { formatDeadline } from "@/lib/format";

interface InvitationView {
  organization_name: string;
  email: string;
  role: "owner" | "service_provider";
  invited_by: string | null;
  expires_at: string;
  account_exists: boolean;
}

// The link in an organization invitation email. Shows who invites whom to
// what; the invitee signs up or logs in with the invited email, then accepts.
export function InvitePage() {
  const { token = "" } = useParams<{ token: string }>();
  const { t } = useI18n();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const { data: invite, isError } = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => apiFetch<InvitationView>(`/account/invitations/${token}`),
    retry: false,
  });

  async function accept() {
    setPending(true);
    setError(null);
    try {
      await apiFetch(`/account/invitations/${token}/accept`, { method: "POST" });
      queryClient.invalidateQueries();
      navigate(user?.role === "owner" ? "/owner/dashboard" : "/service-provider/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("invite.acceptError"));
    } finally {
      setPending(false);
    }
  }

  const here = `/invite/${token}`;
  return (
    <main className="max-w-md mx-auto px-5 py-16">
      <div className="flex justify-end mb-8">
        <LanguageSwitcher />
      </div>
      {isError ? (
        <p className="text-sm text-steel">{t("invite.invalid")}</p>
      ) : !invite ? null : (
        <div className="bg-white border border-border rounded px-6 py-5">
          <h1 className="font-display text-xl font-semibold text-navy mb-2">
            {t("invite.heading").replace("{organization}", invite.organization_name)}
          </h1>
          <p className="text-sm text-steel mb-1">
            {t("invite.body")
              .replace("{inviter}", invite.invited_by ?? t("invite.someone"))
              .replace("{organization}", invite.organization_name)
              .replace("{email}", invite.email)}
          </p>
          <p className="text-xs text-steel-light mb-4">{t("invite.expires").replace("{date}", formatDeadline(invite.expires_at))}</p>
          <ErrorBanner message={error} />
          {user ? (
            user.email.toLowerCase() === invite.email ? (
              <button type="button" onClick={accept} disabled={pending} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-5 py-2.5">
                {t("invite.accept").replace("{organization}", invite.organization_name)}
              </button>
            ) : (
              <p className="text-sm text-amber-dark">{t("invite.wrongAccount").replace("{email}", invite.email)}</p>
            )
          ) : (
            <div className="flex flex-wrap gap-3">
              {!invite.account_exists && (
                <Link
                  to={`/signup?role=${invite.role}&email=${encodeURIComponent(invite.email)}&next=${encodeURIComponent(here)}`}
                  className="bg-navy hover:bg-navy-deep text-white text-sm font-semibold rounded px-5 py-2.5"
                >
                  {t("invite.signUp")}
                </Link>
              )}
              <Link to={`/login?next=${encodeURIComponent(here)}`} className="border border-navy text-navy text-sm font-semibold rounded px-5 py-2.5">
                {t("invite.logIn")}
              </Link>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
