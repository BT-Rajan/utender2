import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ProviderServicesPanel } from "@/components/ProviderServices";
import { apiFetch } from "@/api/client";
import type { ClosureReason, ServiceProviderProfile, OfferStatus, ProjectStatus } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { money } from "@/lib/money";
import { timeLeft, fullDate } from "@/lib/format";
import { outcomeLabel } from "@/components/ClosureOutcome";

interface Preparing {
  project_id: string;
  project_title: string;
  bid_deadline: string;
  availability: "open" | "paused";
  started_at: string | null;
  changed_since: boolean;
  offer_id?: string | null;
  last_saved_at?: string | null; // Stage 5.10
}

interface MyBid {
  project_id: string;
  project_title: string;
  project_address: string;
  project_status: ProjectStatus;
  closure_reason?: ClosureReason | null;
  project_suspended?: boolean;
  bid_deadline: string;
  offer_id: string;
  amount: string;
  offer_status: OfferStatus;
  revision: number;
  submitted_at?: string | null; // Stage 5.16
  updated_at: string;
}

function statusBanner(
  t: (key: string) => string,
): Record<string, { tone: "green" | "blue" | "amber" | "red"; title: string; body: string; cta?: { label: string; href: string } }> {
  const b = "service_provider.dashboard.banner";
  return {
    documents_incomplete: {
      tone: "amber",
      title: t(`${b}.documentsIncompleteTitle`),
      body: t(`${b}.documentsIncompleteBody`),
      cta: { label: t(`${b}.documentsIncompleteCta`), href: "/service-provider/verify" },
    },
    submitted_for_review: {
      tone: "blue",
      title: t(`${b}.submittedTitle`),
      body: t(`${b}.submittedBody`),
      cta: { label: t(`${b}.submittedCta`), href: "/service-provider/status" },
    },
    changes_requested: {
      tone: "red",
      title: t(`${b}.changesRequestedTitle`),
      body: t(`${b}.changesRequestedBody`),
      cta: { label: t(`${b}.changesRequestedCta`), href: "/service-provider/status" },
    },
    payment_required: {
      tone: "amber",
      title: t(`${b}.paymentRequiredTitle`),
      body: t(`${b}.paymentRequiredBody`),
      cta: { label: t(`${b}.paymentRequiredCta`), href: "/service-provider/subscribe" },
    },
    payment_restricted: {
      tone: "red",
      title: t(`${b}.paymentRestrictedTitle`),
      body: t(`${b}.paymentRestrictedBody`),
      cta: { label: t(`${b}.paymentRestrictedCta`), href: "/service-provider/subscribe" },
    },
    suspended: {
      tone: "red",
      title: t(`${b}.suspendedTitle`),
      body: t(`${b}.suspendedBody`),
    },
  };
}

function bannerClasses(tone: "green" | "blue" | "amber" | "red") {
  switch (tone) {
    case "green":
      return "border-green bg-green-tint text-green";
    case "blue":
      return "border-blue bg-blue-tint text-blue";
    case "red":
      return "border-red bg-red-tint text-red";
    default:
      return "border-amber bg-amber/10 text-amber-dark";
  }
}

function offerStatusBadge(status: OfferStatus) {
  switch (status) {
    case "approved":
      return "bg-green-tint text-green";
    case "rejected":
      return "bg-border text-steel";
    case "withdrawn":
      return "bg-border text-steel-light";
    default:
      return "bg-blue-tint text-blue";
  }
}

export function ServiceProviderDashboardPage() {
  const { t, language } = useI18n();
  const { data: profile } = useQuery({
    queryKey: ["service-provider-profile"],
    queryFn: () => apiFetch<ServiceProviderProfile>("/service-provider/profile"),
  });
  const { data: bids } = useQuery({
    queryKey: ["service-provider-my-bids"],
    queryFn: () => apiFetch<MyBid[]>("/service-provider/my-bids"),
    enabled: !!profile,
  });
  // Stage 4.9: opportunities they decided to take part in, with no offer yet.
  const { data: preparing } = useQuery({
    queryKey: ["service-provider-preparing"],
    queryFn: () => apiFetch<Preparing[]>("/service-provider/preparing"),
    enabled: !!profile && profile.verification_status === "approved",
  });

  if (!profile) return <PageLoading />;

  const banner = statusBanner(t)[profile.marketplace_status];
  const isActive = profile.marketplace_status === "verified_active";
  // Counted by the server over every offer (the list itself is paged).
  const { data: summary } = useQuery({
    queryKey: ["service-provider-my-bids-summary"],
    queryFn: () => apiFetch<{ total: number; active: number; won: number }>("/service-provider/my-bids/summary"),
  });
  const activeBids = summary?.active ?? 0;
  const won = summary?.won ?? 0;
  const totalBids = summary?.total ?? 0;

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="mb-6">
        <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("service_provider.roleLabel")}</span>
        <h1 className="font-display text-2xl font-semibold text-navy mb-1">{profile.company_name}</h1>
      </div>

      {banner && (
        <div className={`border border-l-4 rounded px-5 py-4 mb-6 flex items-center justify-between flex-wrap gap-3 ${bannerClasses(banner.tone)}`}>
          <div>
            <div className="font-display font-semibold text-sm">{banner.title}</div>
            <p className="text-[13px] mt-1 opacity-90">{banner.body}</p>
          </div>
          {banner.cta && (
            <Link
              to={banner.cta.href}
              className="bg-navy hover:bg-navy-deep text-white text-xs font-semibold rounded px-4 py-2 whitespace-nowrap"
            >
              {banner.cta.label}
            </Link>
          )}
        </div>
      )}

      <ProviderServicesPanel profile={profile} />

      {isActive && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
            <div className="border border-border bg-white rounded px-4 py-3">
              <div className="font-display text-2xl font-semibold text-navy leading-none">{activeBids}</div>
              <div className="font-mono text-[10px] uppercase tracking-wide text-steel mt-1">{t("service_provider.dashboard.kpiActiveBids")}</div>
            </div>
            <div className="border border-border bg-white rounded px-4 py-3">
              <div className="font-display text-2xl font-semibold text-green leading-none">{won}</div>
              <div className="font-mono text-[10px] uppercase tracking-wide text-steel mt-1">{t("service_provider.dashboard.kpiProjectsWon")}</div>
            </div>
            <div className="border border-border bg-white rounded px-4 py-3">
              <div className="font-display text-2xl font-semibold text-navy leading-none">{totalBids}</div>
              <div className="font-mono text-[10px] uppercase tracking-wide text-steel mt-1">{t("service_provider.dashboard.kpiTotalBids")}</div>
            </div>
          </div>

          {!!preparing?.length && (
            <section className="mb-6" data-testid="preparing">
              <h2 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("participate.preparingHeading")}</h2>
              <ul className="grid gap-2">
                {preparing.map((p) => (
                  <li key={p.project_id} className="tblock rounded px-4 py-2.5 flex items-center justify-between gap-3 text-sm">
                    <Link to={`/service-provider/projects/${p.project_id}/offer`} className="text-navy underline" dir="auto">
                      {p.project_title || t("saved.unavailable")}
                    </Link>
                    <span className="font-mono text-[11px] text-steel">
                      {p.availability === "paused" ? t("postPub.pausedPill") : timeLeft(t, p.bid_deadline)}
                      {p.changed_since && <span className="text-amber-dark"> · {t("participate.changedShort")}</span>}
                      {p.last_saved_at && p.offer_id && <span> · {t("participate.lastSaved")} {fullDate(p.last_saved_at, language)}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <div className="flex items-center justify-between mb-4">
            <h2 className="font-mono text-[11px] uppercase tracking-wide text-navy">{t("service_provider.dashboard.myBids")}</h2>
            <Link to="/service-provider/feed" className="text-xs text-navy underline">
              {t("service_provider.dashboard.browseOpenProjects")}
            </Link>
          </div>

          {!bids?.length ? (
            <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel">
              {t("service_provider.dashboard.noBidsYetPrefix")}{" "}
              <Link to="/service-provider/feed" className="text-navy underline">
                {t("service_provider.dashboard.browseOpenProjects")}
              </Link>
              .
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {bids.map((b) => (
                <Link key={b.offer_id} to={`/service-provider/projects/${b.project_id}/offer`} className="tblock rounded px-5 pt-4">
                  <div className="flex justify-between items-start gap-2">
                    <div>
                      <h3 className="font-display font-semibold text-[15px] mb-0.5">{b.project_title}</h3>
                      <p className="text-[12px] text-steel mb-2">{b.project_address}</p>
                    </div>
                    <span className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded-full whitespace-nowrap ${offerStatusBadge(b.offer_status)}`}>
                      {b.offer_status === "submitted" ? t("service_provider.feed.bidPlaced") : t(`feed.offer_${b.offer_status}`)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between font-mono text-xs">
                    <span className="text-navy font-semibold">{money(b.amount)}</span>
                    <span className="text-steel-light">{b.project_suspended ? t("closure.labelSuspended") : outcomeLabel(t, b.project_status, b.closure_reason)}</span>
                  </div>
                  {/* Stage 5.16: when -- first submitted, and the last change (a revision or the withdrawal). */}
                  <p className="font-mono text-[10.5px] text-steel-light mt-1.5 mb-3" data-testid="bid-timing">
                    {b.submitted_at && `${t("submitOffer.submittedAt")} ${fullDate(b.submitted_at, language)}`}
                    {b.offer_status === "withdrawn"
                      ? ` · ${t("submitOffer.withdrawnAt")} ${fullDate(b.updated_at, language)}`
                      : b.revision > 1 && ` · ${t("submitOffer.revision")} ${b.revision} · ${fullDate(b.updated_at, language)}`}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
