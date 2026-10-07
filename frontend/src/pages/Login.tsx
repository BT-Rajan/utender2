import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ApiError } from "@/api/client";
import { safeNext } from "@/lib/next";

export function LoginPage() {
  const { login } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { notice?: string }; search: string };
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      await login(form.get("email") as string, form.get("password") as string);
      navigate(safeNext(new URLSearchParams(location.search).get("next")) ?? "/");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.login.genericError"));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="max-w-sm mx-auto px-5 py-16">
      <div className="flex items-center justify-between mb-10">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 border-2 border-navy flex items-center justify-center font-display font-bold text-sm text-navy">
            U
          </div>
          <div>
            <div className="font-display font-bold text-lg text-navy leading-none">U-TENDER</div>
            <div className="text-[10px] text-steel uppercase tracking-widest">{t("brand.tagline")}</div>
          </div>
        </div>
        <LanguageSwitcher />
      </div>

      <h1 className="font-display text-xl font-semibold text-navy mb-6">{t("auth.login.heading")}</h1>

      {location.state?.notice && (
        <p className="text-xs bg-blue-tint text-blue border border-blue rounded px-3 py-2.5 mb-4">
          {location.state.notice}
        </p>
      )}
      {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2.5 mb-4">{error}</p>}

      <form onSubmit={handleSubmit} className="grid gap-4">
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.login.email")}
          </label>
          <input type="email" name="email" required className="w-full border border-border rounded px-3 py-2.5 text-sm" />
        </div>
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.login.password")}
          </label>
          <input
            type="password"
            name="password"
            required
            className="w-full border border-border rounded px-3 py-2.5 text-sm"
          />
          <Link to="/forgot-password" className="text-xs text-navy underline mt-1.5 inline-block">
            {t("auth.login.forgotPassword")}
          </Link>
        </div>
        <button
          type="submit"
          disabled={pending}
          className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 mt-2"
        >
          {pending ? t("auth.login.submitting") : t("auth.login.submit")}
        </button>
      </form>

      <p className="text-xs text-steel mt-6">
        {t("auth.login.noAccount")}{" "}
        <Link to="/signup" className="text-navy underline">
          {t("auth.login.signupLink")}
        </Link>
      </p>
    </main>
  );
}
