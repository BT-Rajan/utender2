import { useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

export function ForgotPasswordPage() {
  const { t } = useI18n();
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      await apiFetch("/auth/forgot-password", { method: "POST", body: { email: form.get("email") } });
      setSent(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.forgotPassword.sent"));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="max-w-sm mx-auto px-5 py-16">
      <div className="flex justify-end mb-6">
        <LanguageSwitcher />
      </div>

      <h1 className="font-display text-xl font-semibold text-navy mb-2">{t("auth.forgotPassword.heading")}</h1>
      <p className="text-xs text-steel mb-6">{t("auth.forgotPassword.description")}</p>

      {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2.5 mb-4">{error}</p>}

      {sent ? (
        <p className="text-xs bg-blue-tint text-blue border border-blue rounded px-3 py-2.5 mb-4">
          {t("auth.forgotPassword.sent")}
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="grid gap-4">
          <div>
            <label htmlFor="forgot-email" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
              {t("auth.forgotPassword.email")}
            </label>
            <input id="forgot-email" type="email" name="email" required className="w-full border border-border rounded px-3 py-2.5 text-sm" />
          </div>
          <button
            type="submit"
            disabled={pending}
            className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 mt-2"
          >
            {pending ? t("auth.forgotPassword.submitting") : t("auth.forgotPassword.submit")}
          </button>
        </form>
      )}

      <p className="text-xs text-steel mt-6">
        <Link to="/login" className="text-navy underline">
          {t("auth.forgotPassword.backToLogin")}
        </Link>
      </p>
    </main>
  );
}
