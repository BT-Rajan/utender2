import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ServiceProviderProfile } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { formatMoney, usePricing, type PlanPrice } from "@/lib/publicInfo";
import { fullDate } from "@/lib/format";
import { SupportContact } from "@/components/SupportContact";

function PlanToggle({
  plans,
  plan,
  setPlan,
  onSubscribe,
  pending,
}: {
  plans: PlanPrice[];
  plan: "monthly" | "annual";
  setPlan: (p: "monthly" | "annual") => void;
  onSubscribe: () => void;
  pending: boolean;
}) {
  const { t, language } = useI18n();
  const features = [
    t("service_provider.subscribe.feature1"),
    t("service_provider.subscribe.feature2"),
    t("service_provider.subscribe.feature3"),
    t("service_provider.subscribe.feature4"),
  ];
  // Prices are the live Stripe prices checkout will charge (/public/pricing).
  const monthly = plans.find((p) => p.plan === "monthly");
  const annual = plans.find((p) => p.plan === "annual");
  const selected = plans.find((p) => p.plan === plan) ?? plans[0];
  const savingPercent =
    monthly && annual && monthly.currency === annual.currency
      ? Math.round((1 - Number(annual.amount) / (Number(monthly.amount) * 12)) * 100)
      : 0;
  const perMonth = selected && selected.interval === "year" ? Number(selected.amount) / 12 : Number(selected?.amount);

  return (
    <div>
      {plans.length > 1 && (
        <div className="inline-flex border border-navy rounded-full overflow-hidden mb-6">
          {plans.map((p, i) => (
            <button
              key={p.plan}
              type="button"
              onClick={() => setPlan(p.plan)}
              className={`font-mono text-xs px-4.5 py-2 uppercase tracking-wide ${i > 0 ? "border-s border-navy" : ""} ${selected?.plan === p.plan ? "bg-navy text-white" : "bg-white text-navy"}`}
            >
              {t(`pricing.${p.plan}`)}
              {p.plan === "annual" && savingPercent > 0 && ` — ${t("service_provider.subscribe.save").replace("{percent}", String(savingPercent))}`}
            </button>
          ))}
        </div>
      )}

      <div className="bg-white border border-border border-t-4 border-t-amber rounded px-7 py-7 max-w-md">
        {selected ? (
          <>
            <div className="font-display text-[42px] font-bold text-navy leading-none">
              {formatMoney(perMonth, selected.currency, language)}
              <span className="font-mono text-sm font-normal text-steel"> {t("pricing.perMonth")}</span>
            </div>
            <p className="text-xs text-steel mt-2 mb-5">
              {selected.interval === "year"
                ? t("service_provider.subscribe.priceAnnualNote").replace("{amount}", formatMoney(selected.amount, selected.currency, language))
                : t("service_provider.subscribe.priceMonthlyNote")}
            </p>
          </>
        ) : (
          <div className="mb-5">
            <p className="text-sm text-steel">{t("service_provider.subscribe.billingUnavailable")}</p>
            <SupportContact />
          </div>
        )}
        <ul className="mb-6">
          {features.map((f) => (
            <li key={f} className="flex items-center gap-2 text-[13.5px] py-2 border-t border-border">
              <span className="text-green font-mono font-bold">✓</span> {f}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={onSubscribe}
          disabled={pending || !selected}
          className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-full"
        >
          {t("service_provider.subscribe.start")}
        </button>
      </div>
    </div>
  );
}

export function ServiceProviderSubscribePage() {
  const { t, language } = useI18n();
  const [plan, setPlan] = useState<"monthly" | "annual">("monthly");
  const [error, setError] = useState<string | null>(null);

  const { data: profile } = useQuery({
    queryKey: ["service-provider-profile"],
    queryFn: () => apiFetch<ServiceProviderProfile>("/service-provider/profile"),
  });

  const { data: plans, isLoading: plansLoading } = usePricing();
  // If only one plan is configured, checkout must use that one.
  const checkoutPlan = plans?.some((p) => p.plan === plan) ? plan : (plans?.[0]?.plan ?? plan);

  const checkoutMutation = useMutation({
    mutationFn: () => apiFetch<{ url: string }>(`/billing/checkout-session?plan=${checkoutPlan}`, { method: "POST" }),
    onSuccess: (data) => {
      window.location.href = data.url;
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("service_provider.subscribe.checkoutError")),
  });

  const portalMutation = useMutation({
    mutationFn: () => apiFetch<{ url: string }>("/billing/portal-session", { method: "POST" }),
    onSuccess: (data) => {
      window.location.href = data.url;
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("service_provider.subscribe.portalError")),
  });

  if (!profile || plansLoading) return <PageLoading />;

  const hasRealSubscription = profile.subscription_status === "active" || profile.subscription_status === "trialing";
  // marketplace_status already folds in an admin payment override, so a
  // service provider can be fully active (verified_active) with no Stripe
  // subscription at all — that state gets its own message rather than
  // being lumped in with "Subscribe to bid".
  const isActive = profile.marketplace_status === "verified_active";
  const overrideOnly = isActive && !hasRealSubscription;

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("service_provider.subscribe.eyebrow")}</span>
      <h1 className="font-display text-2xl font-semibold text-navy mb-1">
        {isActive ? t("service_provider.subscribe.headingActive") : t("service_provider.subscribe.headingInactive")}
      </h1>
      <p className="text-[13.5px] text-steel mb-7">
        {isActive ? t("service_provider.subscribe.subheadingActive") : t("service_provider.subscribe.subheadingInactive")}
      </p>

      <ErrorBanner message={error} />

      {/* Stage 9.13: a failed payment is fixed on the existing subscription
          (the billing portal), never by starting a second one. */}
      {!isActive && profile.subscription_status === "past_due" ? (
        <div className="bg-white border border-border border-t-4 border-t-red rounded px-7 py-7 max-w-md">
          <div className="font-display font-semibold text-navy">{t("service_provider.subscribe.pastDueTitle")}</div>
          <p className="text-sm text-steel mt-2">{t("service_provider.subscribe.pastDueBody")}</p>
          <button
            type="button"
            onClick={() => portalMutation.mutate()}
            disabled={portalMutation.isPending}
            className="mt-5 bg-amber hover:bg-amber-dark disabled:opacity-60 text-white text-sm font-semibold rounded px-5 py-2.5"
          >
            {t("service_provider.subscribe.updatePayment")}
          </button>
          <SupportContact />
        </div>
      ) : isActive ? (
        <div className="bg-white border border-border border-t-4 border-t-green rounded px-7 py-7 max-w-md">
          <span className="font-mono text-[10px] uppercase px-2.5 py-1 rounded-full bg-green-tint text-green">
            {overrideOnly ? t("service_provider.subscribe.overrideBadge") : profile.subscription_status}
          </span>
          {overrideOnly && <p className="text-sm text-steel mt-3">{t("service_provider.subscribe.overrideMessage")}</p>}
          {!overrideOnly && profile.subscription_current_period_end && (
            <p className="text-sm text-steel mt-3">
              {/* Stage 9.6: a cancellation already scheduled ends access on that date -- it doesn't renew. */}
              {t(profile.subscription_cancel_at_period_end ? "service_provider.subscribe.ends" : "service_provider.subscribe.renews")}{" "}
              {fullDate(profile.subscription_current_period_end, language, false)}
              {profile.subscription_interval && ` · ${t(profile.subscription_interval === "year" ? "service_provider.subscribe.yearly" : "service_provider.subscribe.monthly")}`}
            </p>
          )}
          {!overrideOnly && (
            <button
              type="button"
              onClick={() => portalMutation.mutate()}
              className="mt-5 border border-navy text-navy hover:bg-navy hover:text-white text-sm font-semibold rounded px-5 py-2.5"
            >
              {t("service_provider.subscribe.manageBilling")}
            </button>
          )}
        </div>
      ) : (
        <>
          <PlanToggle
            plans={plans ?? []}
            plan={checkoutPlan}
            setPlan={setPlan}
            onSubscribe={() => checkoutMutation.mutate()}
            pending={checkoutMutation.isPending}
          />
          <p className="text-xs text-steel-light mt-6 max-w-md">{t("service_provider.subscribe.checkoutNote")}</p>
        </>
      )}
    </main>
  );
}
