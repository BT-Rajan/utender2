import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiFetch } from "@/api/client";
import { FindPerson } from "@/components/AdminSupport";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

type Section<T> = { available: boolean; data: T | null };
type Counts = Record<string, number>;
interface Attention {
  kind: string;
  count: number;
  link: string;
  items: { id: string | null; title: string | null; since: string | null }[];
}
interface Overview {
  as_of: string;
  accounts: Section<{ owners: Counts; providers: Counts }>;
  requirements: Section<{ by_status: Counts; suspended: number; open_with_offers: number; open_without_offers: number }>;
  offers: Section<{ by_status: Counts; submitted_last_7_days: number; on_open_requirements: number }>;
  transactions: Section<{ by_status: Counts; on_hold: number; completion_awaiting_owner: number; awarded_last_7_days: number }>;
  attention: Section<Attention[]>;
  background: Section<{ deadline_reminders: "ok" | "overdue" | "not_determinable"; deadline_reminders_overdue: number; email_delivery: "failing" | "no_failures_recorded" | "not_configured"; email_failures_24h: number; billing_webhook: "configured" | "not_configured"; last_billing_event_at: string | null; backup: "not_configured" | "never_run" | "failing" | "overdue" | "recent"; last_backup_at: string | null; backup_failed_step: string | null }>;
}

function Block({ title, section, children }: { title: string; section: Section<unknown>; children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <section className="bg-white border border-border rounded px-4 py-3" data-testid="ops-section">
      <h2 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{title}</h2>
      {section.available ? children : <p className="text-sm text-red" role="alert">{t("ops.unavailable")}</p>}
    </section>
  );
}

function Rows({ rows }: { rows: ([string, number | string] | [string, number | string, string | undefined])[] }) {
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
      {rows.map(([label, value, help]) => (
        <div key={label} className="contents">
          <dt className="text-steel" title={help}>{label}</dt>
          <dd className="font-mono text-navy text-end">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

// Stage 9.1: the operator's overview -- what needs attention now, then the
// marketplace's state, from the server's authoritative counts. A section the
// server couldn't compute says so; it never reads as zero.
export function AdminOverviewPage() {
  const { t, language } = useI18n();
  const { data, error, isPending, refetch, isFetching } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: () => apiFetch<Overview>("/admin/overview"),
    refetchInterval: 5 * 60 * 1000,
  });
  return (
    <main className="max-w-5xl mx-auto px-5 py-8 text-ink">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
        <h1 className="font-display text-2xl font-semibold text-navy">{t("admin.nav.overview")}</h1>
        <div className="flex items-center gap-3 text-xs text-steel">
          {data && <span>{t("ops.asOf")} {fullDate(data.as_of, language)}</span>}
          <button type="button" onClick={() => void refetch()} disabled={isFetching} className="border border-navy text-navy font-semibold rounded px-3 py-1.5 disabled:opacity-60">
            {t("ops.refresh")}
          </button>
        </div>
      </div>
      <div className="mb-4"><FindPerson /></div>
      {isPending && <p className="text-sm text-steel">{t("ops.loading")}</p>}
      {error && <ErrorBanner message={t("ops.failed")} />}
      {data && (
        <div className="grid gap-4">
          <Block title={t("ops.attention")} section={data.attention}>
            {data.attention.data?.length ? (
              <ul className="grid gap-3">
                {data.attention.data.map((a) => (
                  <li key={a.kind} className="text-sm" data-testid="ops-attention">
                    <div className="font-semibold">
                      {t(`ops.kinds.${a.kind}`)} <span className="font-mono text-amber-dark">({a.count})</span>
                    </div>
                    <ul className="text-xs text-steel mt-1 grid gap-0.5">
                      {a.items.map((i, n) => (
                        <li key={i.id ?? n}>
                          {!a.link ? (
                            <span dir="auto">{i.title ?? "—"}</span>
                          ) : i.id && a.link.endsWith("/") ? (
                            <Link to={`${a.link}${i.id}`} className="text-blue underline" dir="auto">{i.title ?? t("ops.open")}</Link>
                          ) : (
                            <Link to={a.link} className="text-blue underline">{t("ops.open")}</Link>
                          )}
                          {i.since && ` · ${t("ops.since")} ${fullDate(i.since, language)}`}
                        </li>
                      ))}
                      {a.count > a.items.length && <li>{t("ops.more").replace("{n}", String(a.count - a.items.length))}</li>}
                    </ul>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-green">{t("ops.nothing")}</p>
            )}
          </Block>
          <MarketplaceMetrics />
          <div className="grid gap-4 sm:grid-cols-2">
            <Block title={t("ops.background")} section={data.background}>
              {data.background.data && (
                <Rows
                  rows={[
                    [t("ops.reminders"), data.background.data.deadline_reminders === "overdue"
                      ? t("ops.remindersOverdue").replace("{n}", String(data.background.data.deadline_reminders_overdue))
                      : t(`ops.reminders_${data.background.data.deadline_reminders}`)],
                    // Stage 9.10: configured or not, and when Stripe last told us anything -- never "healthy".
                    [t("ops.billing"), data.background.data.billing_webhook === "not_configured"
                      ? t("ops.billingNotConfigured")
                      : data.background.data.last_billing_event_at
                        ? `${t("ops.lastBillingEvent")} ${fullDate(data.background.data.last_billing_event_at, language)}`
                        : t("ops.noBillingEvents")],
                    [t("ops.email"), data.background.data.email_delivery === "failing"
                      ? t("ops.emailFailing").replace("{n}", String(data.background.data.email_failures_24h))
                      : t(`ops.email_${data.background.data.email_delivery}`)],
                    // Stage 9.12: the latest backup run's outcome -- a recent backup isn't proof it restores.
                    [t("ops.backup"), data.background.data.backup === "failing"
                      ? t("ops.backupFailing").replace("{step}", data.background.data.backup_failed_step ?? "?")
                      : data.background.data.backup === "overdue" || data.background.data.backup === "recent"
                        ? `${t(data.background.data.backup === "overdue" ? "ops.backupOverdue" : "ops.backupRecent")} ${data.background.data.last_backup_at ? fullDate(data.background.data.last_backup_at, language) : ""}`
                        : t(`ops.backup_${data.background.data.backup}`)],
                  ]}
                />
              )}
            </Block>
            <Block title={t("ops.accounts")} section={data.accounts}>
              {data.accounts.data && (
                <Rows
                  rows={[
                    [t("ops.owners"), data.accounts.data.owners.total],
                    [t("ops.ownersActive"), data.accounts.data.owners.active],
                    [t("ops.awaitingReview"), data.accounts.data.owners.awaiting_review],
                    [t("ops.providers"), data.accounts.data.providers.total],
                    [t("ops.canBid"), data.accounts.data.providers.can_bid],
                    [t("ops.withoutPayment"), data.accounts.data.providers.approved_without_payment],
                    [t("ops.paymentFailed"), data.accounts.data.providers.payment_failed],
                    [t("ops.awaitingReviewProviders"), data.accounts.data.providers.awaiting_review],
                    [t("ops.suspended"), data.accounts.data.owners.suspended + data.accounts.data.providers.suspended],
                  ]}
                />
              )}
            </Block>
            <Block title={t("ops.requirements")} section={data.requirements}>
              {data.requirements.data && (
                <Rows
                  rows={[
                    [t("ops.open"), data.requirements.data.by_status.open],
                    [t("ops.openWithOffers"), data.requirements.data.open_with_offers],
                    [t("ops.openWithoutOffers"), data.requirements.data.open_without_offers],
                    [t("ops.drafts"), data.requirements.data.by_status.draft],
                    [t("ops.awaitingDecision"), data.requirements.data.by_status.closed + data.requirements.data.by_status.under_evaluation],
                    [t("ops.awarded"), data.requirements.data.by_status.awarded],
                    [t("ops.endedWithoutAward"), data.requirements.data.by_status.no_award + data.requirements.data.by_status.canceled + data.requirements.data.by_status.expired],
                    [t("ops.suspended"), data.requirements.data.suspended],
                  ]}
                />
              )}
            </Block>
            <Block title={t("ops.offers")} section={data.offers}>
              {data.offers.data && (
                <Rows
                  rows={[
                    [t("ops.onOpen"), data.offers.data.on_open_requirements],
                    [t("ops.last7"), data.offers.data.submitted_last_7_days],
                    [t("ops.withdrawn"), data.offers.data.by_status.withdrawn ?? 0],
                  ]}
                />
              )}
            </Block>
            <Block title={t("ops.transactions")} section={data.transactions}>
              {data.transactions.data && (
                <Rows
                  rows={[
                    [t("ops.preparing"), data.transactions.data.by_status.preparing],
                    [t("ops.active"), data.transactions.data.by_status.active],
                    [t("ops.onHold"), data.transactions.data.on_hold],
                    [t("ops.completionAwaiting"), data.transactions.data.completion_awaiting_owner],
                    [t("ops.completed"), data.transactions.data.by_status.completed],
                    [t("ops.terminated"), data.transactions.data.by_status.terminated],
                    [t("ops.awardedLast7"), data.transactions.data.awarded_last_7_days],
                  ]}
                />
              )}
            </Block>
          </div>
        </div>
      )}
    </main>
  );
}


type Counts9 = Record<string, number | null>;
interface Metrics {
  since: string | null;
  definitions: Record<string, string>;
  activity: Section<Counts9>;
  requirement_funnel: Section<Counts9>;
  provider_funnel: Section<Counts9>;
  subscriptions: Section<Counts9>;
}

const PERIODS = ["today", "7d", "30d", "month", "all"] as const;

// Stage 9.9: what happened in a period (UTC, server clock), the period's
// requirement and provider funnels, and today's subscription picture -- counts
// from the records, each with its definition on hover. No prices or names.
export function MarketplaceMetrics() {
  const { t, language } = useI18n();
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>("30d");
  const { data, error } = useQuery({ queryKey: ["admin-metrics", period], queryFn: () => apiFetch<Metrics>(`/admin/metrics?period=${period}`) });
  const pct = (n: number | null | undefined, of: number | null | undefined) => (n == null ? "—" : of ? `${n} (${Math.round((100 * n) / of)}%)` : String(n));
  const d = data?.definitions ?? {};
  return (
    <section className="grid gap-4" data-testid="marketplace-metrics">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h2 className="font-display text-lg font-semibold text-navy">{t("metrics.heading")}</h2>
        <div className="flex gap-1" role="group" aria-label={t("metrics.period")}>
          {PERIODS.map((p) => (
            <button key={p} type="button" onClick={() => setPeriod(p)} aria-pressed={period === p}
              className={`font-mono text-[11px] rounded px-2.5 py-1 border ${period === p ? "border-navy bg-navy text-white" : "border-border text-steel"}`}>
              {t(`metrics.periods.${p}`)}
            </button>
          ))}
        </div>
      </div>
      {data?.since && <p className="text-xs text-steel">{t("metrics.since")} {fullDate(data.since, language)} (UTC)</p>}
      {error && <ErrorBanner message={t("ops.failed")} />}
      {data && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Block title={t("metrics.activity")} section={data.activity}>
            {data.activity.data && (
              <Rows rows={[
                [t("metrics.newAccounts"), data.activity.data.new_accounts ?? "—", d.new_accounts],
                [t("metrics.published"), data.activity.data.requirements_published ?? "—", d.requirements_published],
                [t("metrics.offers"), data.activity.data.offers_submitted ?? "—", d.offers_submitted],
                [t("metrics.awards"), data.activity.data.awards ?? "—", d.awards],
                [t("metrics.completed"), data.activity.data.transactions_completed ?? "—", d.transactions_completed],
                [t("metrics.reviews"), data.activity.data.reviews ?? "—", d.reviews],
                [t("metrics.activePeople"), data.activity.data.active_people ?? "—", d.active_people],
                [t("metrics.returning"), data.activity.data.returning_people ?? "—", d.returning_people],
              ]} />
            )}
          </Block>
          <Block title={t("metrics.requirementFunnel")} section={data.requirement_funnel}>
            {data.requirement_funnel.data && (() => {
              const f = data.requirement_funnel.data;
              return (
                <Rows rows={[
                  [t("metrics.published"), f.published ?? "—", d.requirement_funnel],
                  [t("metrics.receivedOffers"), pct(f.received_offers, f.published)],
                  [t("metrics.awarded"), pct(f.awarded, f.published)],
                  [t("metrics.completed"), pct(f.completed, f.published)],
                  [t("metrics.endedWithoutAward"), pct(f.ended_without_award, f.published)],
                ]} />
              );
            })()}
          </Block>
          <Block title={t("metrics.providerFunnel")} section={data.provider_funnel}>
            {data.provider_funnel.data && (() => {
              const f = data.provider_funnel.data;
              return (
                <Rows rows={[
                  [t("metrics.registered"), f.registered ?? "—", d.provider_funnel],
                  [t("metrics.verified"), pct(f.verified, f.registered)],
                  [t("metrics.ableToBid"), pct(f.able_to_bid, f.registered)],
                  [t("metrics.participated"), pct(f.submitted_an_offer, f.registered)],
                ]} />
              );
            })()}
          </Block>
          <Block title={t("metrics.subscriptions")} section={data.subscriptions}>
            {data.subscriptions.data && (
              <Rows rows={[
                [t("metrics.paying"), data.subscriptions.data.paying ?? "—", d.subscriptions],
                [t("metrics.overrideOnly"), data.subscriptions.data.override_only ?? "—"],
                [t("metrics.pastDue"), data.subscriptions.data.past_due ?? "—"],
                [t("metrics.cancelled"), data.subscriptions.data.cancelled_or_expired ?? "—"],
                [t("metrics.neverSubscribed"), data.subscriptions.data.never_subscribed ?? "—"],
              ]} />
            )}
          </Block>
        </div>
      )}
    </section>
  );
}
