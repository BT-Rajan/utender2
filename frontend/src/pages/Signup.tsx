import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { ApiError } from "@/api/client";
import { formatPlanPrice, parseRoleSlug, roleSlug, usePricing, usePublicCms, type SignupRole } from "@/lib/publicInfo";

function RoleHint({ role }: { role: SignupRole | null }) {
  const { t, language } = useI18n();
  const { data: cms } = usePublicCms(language);
  const { data: plans } = usePricing(role === "contractor");
  if (!role) return <p className="text-xs mt-1.5 text-amber-dark">{t("auth.signup.chooseRole")}</p>;
  const hint = cms?.[role === "owner" ? "signup_owner_hint" : "signup_provider_hint"];
  const prices = role === "contractor" && plans && plans.length > 0 ? plans.map((p) => formatPlanPrice(p, language, t)).join(" · ") : null;
  return (
    <p className="text-xs mt-1.5 text-steel">
      {hint}
      {prices && <span className="block text-navy font-semibold mt-0.5">{prices}</span>}
    </p>
  );
}

function RoleFields({
  role,
  setRole,
  clearRole,
}: {
  role: SignupRole | null;
  setRole: (r: SignupRole) => void;
  clearRole: () => void;
}) {
  const { t } = useI18n();
  const roleName = (r: SignupRole) => (r === "owner" ? t("auth.signup.propertyOwner") : t("auth.signup.contractor"));
  return (
    <>
      {role ? (
        // Role arrived from the landing page (or was just picked): show it as
        // settled, not as a choice to make again.
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">
            {t("auth.signup.signingUpAs")}
          </label>
          <div className="flex items-center justify-between border border-navy rounded px-3 py-2.5">
            <span className="font-display font-semibold text-navy">{roleName(role)}</span>
            <button type="button" onClick={clearRole} className="text-xs text-steel underline">
              {t("auth.signup.changeRole")}
            </button>
          </div>
          <RoleHint role={role} />
        </div>
      ) : (
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">
            {t("auth.signup.iAmA")}
          </label>
          <div className="grid grid-cols-2 gap-2">
            {(["owner", "contractor"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                className="border border-navy rounded px-3 py-2.5 text-sm font-semibold text-navy hover:bg-navy hover:text-white"
              >
                {roleName(r)}
              </button>
            ))}
          </div>
          <RoleHint role={null} />
        </div>
      )}

      {role === "contractor" && (
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.signup.companyName")}
          </label>
          <input name="company_name" required className="w-full border border-border rounded px-3 py-2.5 text-sm" />
          <p className="text-xs text-steel-light mt-1">{t("auth.signup.companyNameHint")}</p>
        </div>
      )}
    </>
  );
}

export function SignupPage() {
  const { signup } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // The role chosen on the landing page arrives as ?role=owner or
  // ?role=service_provider. With no (or an unknown) role nothing is
  // preselected: the visitor picks one of the two here, never a guess.
  const roleParam = searchParams.get("role");
  const role = parseRoleSlug(roleParam);
  const setRole = (r: SignupRole) => setSearchParams({ role: roleSlug(r) }, { replace: true });
  const clearRole = () => setSearchParams({}, { replace: true });

  // Normalise legacy (?role=contractor) or unknown values so the URL always
  // shows the canonical slug, or nothing.
  useEffect(() => {
    if (roleParam === null) return;
    const canonical = role ? roleSlug(role) : null;
    if (roleParam !== canonical) setSearchParams(canonical ? { role: canonical } : {}, { replace: true });
  }, [roleParam, role, setSearchParams]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!role) {
      setError(t("auth.signup.chooseRole"));
      return;
    }
    setError(null);
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      const me = await signup({
        email: form.get("email") as string,
        password: form.get("password") as string,
        full_name: form.get("full_name") as string,
        role,
        company_name: (form.get("company_name") as string) || undefined,
      });
      // Route by the role the backend persisted, not by what this form sent.
      navigate(me.role === "owner" ? "/owner/verify" : "/contractor/verify");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("auth.signup.genericError"));
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

      <h1 className="font-display text-xl font-semibold text-navy mb-6">{t("auth.signup.heading")}</h1>

      {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2.5 mb-4">{error}</p>}

      <form onSubmit={handleSubmit} className="grid gap-4">
        <RoleFields role={role} setRole={setRole} clearRole={clearRole} />

        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.signup.fullName")}
          </label>
          <input name="full_name" required className="w-full border border-border rounded px-3 py-2.5 text-sm" />
        </div>
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.signup.email")}
          </label>
          <input type="email" name="email" required className="w-full border border-border rounded px-3 py-2.5 text-sm" />
        </div>
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1">
            {t("auth.signup.password")}
          </label>
          <input
            type="password"
            name="password"
            required
            minLength={8}
            className="w-full border border-border rounded px-3 py-2.5 text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={pending || !role}
          className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 mt-2"
        >
          {pending ? t("auth.signup.submitting") : t("auth.signup.submit")}
        </button>
      </form>

      <p className="text-xs text-steel mt-6">
        {t("auth.signup.haveAccount")}{" "}
        <Link to="/login" className="text-navy underline">
          {t("auth.signup.loginLink")}
        </Link>
      </p>
    </main>
  );
}
