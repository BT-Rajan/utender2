import { useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import { apiFetch, ApiError } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { StakeholderSummary, useIdentity } from "@/components/Stakeholder";
import { AppHeader } from "@/components/AppHeader";
import { OrganizationMembers } from "@/components/OrganizationMembers";

const ROLE_HOME: Record<string, { label: string; href: string }> = {
  owner: { label: "Owner", href: "/owner/dashboard" },
  service_provider: { label: "ServiceProvider", href: "/service-provider/dashboard" },
  admin: { label: "Site Admin", href: "/admin/overview" },
};

function EmailVerifyBanner() {
  const { user, refresh } = useAuth();
  const { t } = useI18n();
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);

  if (!user || user.email_verified) return null;

  async function handleResend() {
    setPending(true);
    try {
      await apiFetch("/auth/request-email-verification", { method: "POST" });
      setSent(true);
      refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 text-xs bg-blue-tint text-blue border border-blue rounded px-3 py-2.5 mb-6">
      <span>{sent ? t("auth.emailVerifyBanner.sent") : t("auth.emailVerifyBanner.message")}</span>
      {!sent && (
        <button type="button" onClick={handleResend} disabled={pending} className="underline font-semibold shrink-0">
          {t("auth.emailVerifyBanner.resend")}
        </button>
      )}
    </div>
  );
}

function ChangePasswordForm() {
  const { t } = useI18n();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: {
          current_password: form.get("current_password"),
          new_password: form.get("new_password"),
        },
      });
      setSuccess(true);
      e.currentTarget.reset();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.changePassword.heading"));
    } finally {
      setPending(false);
    }
  }

  return (
    <div>
      <h2 className="font-display text-lg font-semibold text-navy mb-4">{t("auth.changePassword.heading")}</h2>
      {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2.5 mb-4">{error}</p>}
      {success && (
        <p className="text-xs bg-blue-tint text-blue border border-blue rounded px-3 py-2.5 mb-4">
          {t("auth.changePassword.success")}
        </p>
      )}
      <form onSubmit={handleSubmit} className="grid gap-4 max-w-sm">
        <div>
          <label htmlFor="account-current-password" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.changePassword.currentPassword")}
          </label>
          <input
            id="account-current-password"
            type="password"
            name="current_password"
            required
            className="w-full border border-border rounded px-3 py-2.5 text-sm"
          />
        </div>
        <div>
          <label htmlFor="account-new-password" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.changePassword.newPassword")}
          </label>
          <input
            id="account-new-password"
            type="password"
            name="new_password"
            required
            minLength={8}
            className="w-full border border-border rounded px-3 py-2.5 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={pending}
          className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 mt-2 w-fit"
        >
          {pending ? t("auth.changePassword.submitting") : t("auth.changePassword.submit")}
        </button>
      </form>
    </div>
  );
}

// Changing the sign-in email: a code goes to the CURRENT address first, so
// someone who only has a signed-in browser can't quietly move the account.
function ChangeEmailForm() {
  const { t } = useI18n();
  const { refresh } = useAuth();
  const [step, setStep] = useState<"ask" | "confirm" | "done">("ask");
  const [sentTo, setSentTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleAsk(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      const r = await apiFetch<{ sent_to: string }>("/auth/email-change/request", {
        method: "POST",
        body: { new_email: form.get("new_email"), current_password: form.get("current_password") },
      });
      setSentTo(r.sent_to);
      setStep("confirm");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.changeEmail.heading"));
    } finally {
      setPending(false);
    }
  }

  async function handleConfirm(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      await apiFetch("/auth/email-change/confirm", { method: "POST", body: { code: String(form.get("code") ?? "").trim() } });
      setStep("done");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.changeEmail.heading"));
    } finally {
      setPending(false);
    }
  }

  const input = "w-full border border-border rounded px-3 py-2.5 text-sm";
  const label = "block font-mono text-[11px] uppercase tracking-wide text-steel mb-1";
  const button = "bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 mt-2 w-fit";

  return (
    <div className="bg-white border border-border rounded px-5 py-4.5 max-w-xl mt-8" data-testid="change-email">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("auth.changeEmail.heading")}</h2>
      {error && <div role="alert" className="text-xs text-red bg-red-tint border border-red rounded px-3 py-2 mb-4">{error}</div>}
      {step === "ask" && (
        <>
          <p className="text-[13px] text-steel mb-3">{t("auth.changeEmail.intro")}</p>
          <form onSubmit={handleAsk} className="flex flex-col gap-3.5">
            <div>
              <label htmlFor="account-new-email" className={label}>{t("auth.changeEmail.newEmail")}</label>
              <input id="account-new-email" type="email" name="new_email" required className={input} />
            </div>
            <div>
              <label htmlFor="account-email-password" className={label}>{t("auth.changeEmail.currentPassword")}</label>
              <input id="account-email-password" type="password" name="current_password" required className={input} />
            </div>
            <button type="submit" disabled={pending} className={button}>{pending ? t("auth.changeEmail.sending") : t("auth.changeEmail.sendCode")}</button>
          </form>
          <p className="text-[12px] text-steel mt-4">{t("auth.changeEmail.lostAccess")}</p>
        </>
      )}
      {step === "confirm" && (
        <form onSubmit={handleConfirm} className="flex flex-col gap-3.5">
          <p className="text-[13px] text-steel">{t("auth.changeEmail.codeSent")} <strong dir="ltr">{sentTo}</strong></p>
          <div>
            <label htmlFor="account-email-code" className={label}>{t("auth.changeEmail.code")}</label>
            <input id="account-email-code" name="code" required inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} className={`${input} tracking-[0.3em] font-mono`} />
          </div>
          <div className="flex gap-3 items-center">
            <button type="submit" disabled={pending} className={button}>{pending ? t("auth.changeEmail.confirming") : t("auth.changeEmail.confirm")}</button>
            <button type="button" onClick={() => { setStep("ask"); setError(null); }} className="text-xs underline text-steel mt-2">{t("auth.changeEmail.back")}</button>
          </div>
        </form>
      )}
      {step === "done" && <p className="text-[13px] text-green">{t("auth.changeEmail.success")}</p>}
    </div>
  );
}

// Who is logged in, and who they act as on the marketplace.
function IdentityCard() {
  const { t } = useI18n();
  const { data: identity } = useIdentity();
  if (!identity?.stakeholder) return null;
  return (
    <section className="bg-white border border-border rounded px-5 py-4.5 mb-8 max-w-xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("stakeholder.heading")}</h2>
      <p className="text-[13px] text-steel mb-3">
        {identity.person.full_name} · {identity.person.email}
      </p>
      <StakeholderSummary stakeholder={identity.stakeholder} />
    </section>
  );
}

function MembersIfOrganization() {
  const { data: identity } = useIdentity();
  return identity?.acting_as?.kind === "organization" ? <OrganizationMembers /> : null;
}

export function AccountPage() {
  const { user } = useAuth();
  const roleInfo = ROLE_HOME[user?.role ?? "owner"];

  return (
    <div className="min-h-screen">
      <AppHeader roleLabel={roleInfo.label} homeHref={roleInfo.href} />
      <main className="max-w-5xl mx-auto px-5 py-8">
        <EmailVerifyBanner />
        <IdentityCard />
        <MembersIfOrganization />
        <ChangePasswordForm />
        <ChangeEmailForm />
      </main>
    </div>
  );
}
