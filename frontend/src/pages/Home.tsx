import type { ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import { apiFetch } from "@/api/client";
import {
  formatPlanPrice,
  signupPath,
  usePricing,
  usePublicCms,
  usePublicRequirements,
  type PlanPrice,
  type PublicRequirement,
  type SignupRole,
} from "@/lib/publicInfo";

interface PublicStats {
  open_tenders: number;
  verified_contractors: number;
  awarded_projects: number;
  total_awarded_value: string;
}

function Label({ children }: { children: ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-wide text-steel mb-1">{children}</div>;
}

// Copy comes from the admin-editable CMS (home_owner_* / home_provider_*);
// the document checklist and the prices underneath it are live data, so
// they stay correct whatever an admin writes in the copy.
function RoleCard({
  role,
  cms,
  documents,
  plans,
}: {
  role: SignupRole;
  cms: Record<string, string>;
  documents: PublicRequirement[] | undefined;
  plans: PlanPrice[] | undefined;
}) {
  const { t, language } = useI18n();
  const k = role === "owner" ? "home_owner" : "home_provider";
  const steps = [1, 2, 3, 4].map((n) => cms[`${k}_step_${n}`]).filter(Boolean);
  return (
    <div className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-6 flex flex-col">
      <h3 className="font-display text-xl font-semibold text-navy mb-2">{cms[`${k}_title`]}</h3>
      <p className="text-[14px] text-steel mb-5">{cms[`${k}_who`]}</p>

      {steps.length > 0 && (
        <>
          <Label>{t("home.stepsLabel")}</Label>
          <ol className="mb-5">
            {steps.map((step, i) => (
              <li key={i} className="flex gap-2.5 text-[13.5px] py-1.5 border-t border-border">
                <span className="font-mono font-bold text-amber-dark">{i + 1}</span> {step}
              </li>
            ))}
          </ol>
        </>
      )}

      <Label>{t("home.afterLabel")}</Label>
      <p className="text-[13.5px] text-steel mb-2">{cms[`${k}_after`]}</p>
      {documents && documents.length > 0 && (
        <ul className="mb-4 text-[13px] text-navy list-disc ps-5">
          {documents.map((d) => (
            <li key={d.name}>
              {d.name}
              {!d.is_required && <span className="text-steel-light"> ({t("home.optional")})</span>}
              {d.description && <span className="block text-[12px] text-steel">{d.description}</span>}
            </li>
          ))}
        </ul>
      )}
      {documents && documents.length === 0 && <p className="text-[13px] text-steel mb-4">{t("home.noDocuments")}</p>}

      <Label>{t("home.costLabel")}</Label>
      <p className={`text-[13.5px] mb-2 ${role === "contractor" ? "text-navy font-semibold" : "text-steel"}`}>{cms[`${k}_cost`]}</p>
      {role === "contractor" && plans && (
        <ul className="mb-4 text-[13.5px] text-navy font-semibold">
          {plans.length > 0 ? (
            plans.map((p) => (
              <li key={p.plan}>
                {t(`pricing.${p.plan}`)}: {formatPlanPrice(p, language, t)}
              </li>
            ))
          ) : (
            <li className="font-normal text-steel">{t("pricing.unavailable")}</li>
          )}
        </ul>
      )}

      <Link
        to={signupPath(role)}
        className="mt-auto bg-amber hover:bg-amber-dark text-white text-sm font-semibold rounded px-5 py-2.5 text-center"
      >
        {cms[`${k}_cta`]}
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

  const { data: cms } = usePublicCms(language, !user);
  const { data: ownerDocs } = usePublicRequirements("owner", !user);
  const { data: providerDocs } = usePublicRequirements("contractor", !user);
  const { data: plans } = usePricing(!user);
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
        {cms ? (
          <>
            <h2 className="font-display text-2xl font-semibold text-navy mb-2 text-center">{cms.home_roles_heading}</h2>
            <p className="text-[14px] text-steel mb-7 text-center max-w-2xl mx-auto">{cms.home_roles_intro}</p>
            <div className="grid sm:grid-cols-2 gap-4">
              <RoleCard role="owner" cms={cms} documents={ownerDocs} plans={plans} />
              <RoleCard role="contractor" cms={cms} documents={providerDocs} plans={plans} />
            </div>
          </>
        ) : (
          // Content couldn't load (API down) — still give both signup paths.
          <div className="flex items-center justify-center gap-3">
            <Link to={signupPath("owner")} className="border border-navy text-navy rounded px-5 py-2.5 text-sm font-semibold">
              {t("auth.signup.propertyOwner")}
            </Link>
            <Link to={signupPath("contractor")} className="border border-navy text-navy rounded px-5 py-2.5 text-sm font-semibold">
              {t("auth.signup.contractor")}
            </Link>
          </div>
        )}
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
