import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

export function ResetPasswordPage() {
  const { t } = useI18n();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(token ? null : t("auth.resetPassword.missingToken"));
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      await apiFetch("/auth/reset-password", {
        method: "POST",
        body: { token, new_password: form.get("new_password") },
      });
      setSuccess(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.resetPassword.invalidToken"));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="max-w-sm mx-auto px-5 py-16">
      <div className="flex justify-end mb-6">
        <LanguageSwitcher />
      </div>

      <h1 className="font-display text-xl font-semibold text-navy mb-6">{t("auth.resetPassword.heading")}</h1>

      {success ? (
        <>
          <p className="text-xs bg-blue-tint text-blue border border-blue rounded px-3 py-2.5 mb-4">
            {t("auth.resetPassword.success")}
          </p>
          <Link
            to="/login"
            className="inline-block bg-amber hover:bg-amber-dark text-white font-semibold text-sm rounded px-5 py-2.5"
          >
            {t("auth.resetPassword.goToLogin")}
          </Link>
        </>
      ) : (
        <>
          {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2.5 mb-4">{error}</p>}
          {token && (
            <form onSubmit={handleSubmit} className="grid gap-4">
              <div>
                <label htmlFor="reset-new-password" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
                  {t("auth.resetPassword.newPassword")}
                </label>
                <input
                  id="reset-new-password"
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
                className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 mt-2"
              >
                {pending ? t("auth.resetPassword.submitting") : t("auth.resetPassword.submit")}
              </button>
            </form>
          )}
          <p className="text-xs text-steel mt-6">
            <Link to="/forgot-password" className="text-navy underline">
              {t("auth.resetPassword.requestNew")}
            </Link>
          </p>
        </>
      )}
    </main>
  );
}
