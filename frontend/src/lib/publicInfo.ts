import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { Language } from "@/i18n/I18nContext";

// Live facts a visitor needs before registering, served by /public/*:
// subscription prices come straight from the Stripe prices checkout charges,
// and the verification checklist from the admin-managed document
// requirements. Never hardcode either in copy — read them from here.

export type SignupRole = "owner" | "service_provider";

// Step 1 -> Step 2 handoff. The landing page's role CTAs link to
// /signup?role=owner or /signup?role=service_provider; the signup form
// sends that same role value to POST /auth/signup, which persists it.
export function signupPath(role: SignupRole): string {
  return `/signup?role=${role}`;
}

export function parseRole(value: string | null): SignupRole | null {
  return value === "owner" || value === "service_provider" ? value : null;
}

export interface PlanPrice {
  plan: "monthly" | "annual";
  amount: string;
  currency: string;
  interval: string;
  interval_count: number;
}

export interface PublicRequirement {
  name: string;
  description: string | null;
  is_required: boolean;
}

export function usePublicCms(language: Language, enabled = true) {
  return useQuery({
    queryKey: ["public-cms", language],
    queryFn: () => apiFetch<Record<string, string>>(`/public/cms?language=${language}`),
    enabled,
  });
}

export function usePricing(enabled = true) {
  return useQuery({
    queryKey: ["public-pricing"],
    queryFn: () => apiFetch<{ plans: PlanPrice[] }>("/public/pricing"),
    select: (data) => data.plans,
    staleTime: 5 * 60_000,
    enabled,
  });
}

export function usePublicRequirements(role: SignupRole, enabled = true) {
  return useQuery({
    queryKey: ["public-requirements", role],
    queryFn: () => apiFetch<PublicRequirement[]>(`/public/requirements?role=${role}`),
    enabled,
  });
}

export function formatMoney(amount: number | string, currency: string, language: Language): string {
  const value = Number(amount);
  try {
    return new Intl.NumberFormat(language, {
      style: "currency",
      currency: currency.toUpperCase(),
      maximumFractionDigits: Number.isInteger(value) ? 0 : undefined,
    }).format(value);
  } catch {
    return `${value} ${currency.toUpperCase()}`;
  }
}

// "$79 / month", "$804 / year" — the interval suffix comes from the
// dictionary so it's translated.
export function formatPlanPrice(plan: PlanPrice, language: Language, t: (key: string) => string): string {
  const suffix = plan.interval === "year" ? t("pricing.perYear") : t("pricing.perMonth");
  return `${formatMoney(plan.amount, plan.currency, language)} ${suffix}`;
}
