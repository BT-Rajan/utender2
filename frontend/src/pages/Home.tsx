import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { apiFetch } from "@/api/client";

interface PublicStats {
  open_tenders: number;
  verified_contractors: number;
  awarded_projects: number;
  total_awarded_value: string;
}

type SignupRole = "owner" | "contractor";

function RoleCard({ role, t }: { role: SignupRole; t: (key: string) => string }) {
  const k = role === "owner" ? "owner" : "provider";
  const steps = [1, 2, 3, 4].map((n) => t(`home.${k}Step${n}`));
  return (
    <div className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-6 flex flex-col">
      <h3 className="font-display text-xl font-semibold text-navy mb-2">{t(`home.${k}Title`)}</h3>
      <p className="text-[14px] text-steel mb-5">{t(`home.${k}Who`)}</p>

      <div className="font-mono text-[10px] uppercase tracking-wide text-steel mb-2">{t("home.stepsLabel")}</div>
      <ol className="mb-5">
        {steps.map((step, i) => (
          <li key={step} className="flex gap-2.5 text-[13.5px] py-1.5 border-t border-border">
            <span className="font-mono font-bold text-amber-dark">{i + 1}</span> {step}
          </li>
        ))}
      </ol>

      <div className="font-mono text-[10px] uppercase tracking-wide text-steel mb-1">{t("home.afterLabel")}</div>
      <p className="text-[13.5px] text-steel mb-4">{t(`home.${k}After`)}</p>

      <div className="font-mono text-[10px] uppercase tracking-wide text-steel mb-1">{t("home.costLabel")}</div>
      <p className={`text-[13.5px] mb-6 ${role === "contractor" ? "text-navy font-semibold" : "text-steel"}`}>
        {t(`home.${k}Cost`)}
      </p>

      <Link
        to={`/signup?role=${role}`}
        className="mt-auto bg-amber hover:bg-amber-dark text-white text-sm font-semibold rounded px-5 py-2.5 text-center"
      >
        {t(`home.${k}Cta`)}
      </Link>
    </div>
  );
}

function StatCard({ value, label }: { value: string; label: string }) {
  return (
    <div className="border border-border bg-white rounded px-5 py-4 text-center">
      <div className="font-display text-3xl font-bold text-navy leading-none">{value}</div>
      <div className="font-mono text-[10px] uppercase tracking-wide text-steel mt-2">{label}</div>
    </div>
  );
}

export function HomePage() {
  const { user, loading } = useAuth();
  const { t, language } = useI18n();

  const { data: cms } = useQuery({
    queryKey: ["public-cms", language],
    queryFn: () => apiFetch<Record<string, string>>(`/public/cms?language=${language}`),
    enabled: !user,
  });
  const { data: stats } = useQuery({
    queryKey: ["public-stats"],
    queryFn: () => apiFetch<PublicStats>("/public/stats"),
    enabled: !user,
  });

  if (loading) return null;

  if (user) {
    if (user.role === "admin") return <Navigate to="/admin/requirements" replace />;
    if (user.role === "owner") return <Navigate to="/owner/dashboard" replace />;
    // The contractor dashboard itself branches on marketplace_status —
    // documents incomplete, pending review, payment required, active, or
    // suspended all land there and get the right prompt.
    return <Navigate to="/contractor/dashboard" replace />;
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-14">
      <div className="flex items-center justify-between mb-14">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 border-2 border-navy flex items-center justify-center font-display font-bold text-navy">
            U
          </div>
          <div className="font-display font-bold text-lg text-navy leading-none">U-TENDER</div>
        </div>
        <div className="flex items-center gap-3">
          <LanguageSwitcher />
          <Link to="/login" className="text-sm text-navy font-semibold hover:underline">
            {t("home.login")}
          </Link>
          <Link to="/signup" className="bg-amber hover:bg-amber-dark text-white text-sm font-semibold rounded px-4 py-2">
            {t("home.signup")}
          </Link>
        </div>
      </div>

      <div className="text-center max-w-2xl mx-auto mb-14">
        <h1 className="font-display text-3xl sm:text-4xl font-bold text-navy mb-4 leading-tight">
          {cms?.hero_heading ?? t("brand.tagline")}
        </h1>
        <p className="text-[15px] text-steel mb-8">{cms?.hero_subheading ?? ""}</p>
        <div className="flex items-center justify-center gap-3">
          <a href="#roles" className="bg-amber hover:bg-amber-dark text-white text-sm font-semibold rounded px-6 py-3">
            {t("home.signup")}
          </a>
          <Link
            to="/login"
            className="border border-navy text-navy hover:bg-navy hover:text-white text-sm font-semibold rounded px-6 py-3"
          >
            {t("home.login")}
          </Link>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-14">
          <StatCard value={String(stats.open_tenders)} label={t("home.statOpen")} />
          <StatCard value={String(stats.verified_contractors)} label={t("home.statVerified")} />
          <StatCard value={String(stats.awarded_projects)} label={t("home.statAwarded")} />
        </div>
      )}

      <section id="roles" className="mb-14 scroll-mt-6">
        <h2 className="font-display text-2xl font-semibold text-navy mb-2 text-center">{t("home.rolesHeading")}</h2>
        <p className="text-[14px] text-steel mb-7 text-center max-w-2xl mx-auto">{t("home.rolesIntro")}</p>
        <div className="grid sm:grid-cols-2 gap-4">
          <RoleCard role="owner" t={t} />
          <RoleCard role="contractor" t={t} />
        </div>
      </section>

      {(cms?.how_it_works_title || cms?.how_it_works_body) && (
        <div className="bg-white border border-border rounded px-7 py-7 max-w-2xl mx-auto">
          <h2 className="font-display text-xl font-semibold text-navy mb-3">{cms.how_it_works_title}</h2>
          <p className="text-[14px] text-steel leading-relaxed">{cms.how_it_works_body}</p>
        </div>
      )}
    </main>
  );
}
