import type { ReactNode } from "react";
import { TrackRecord } from "@/components/TrackRecord";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { Offer, OfferComparison } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";
import { money } from "@/lib/money";
import { formatWorkTiming } from "@/lib/dates";

// Stage 6.6: the owner's chosen offers on one requirement, side by side --
// each exactly as its provider submitted it (nothing recalculated,
// normalised, scored or ranked), in the order the owner chose. Rows where
// the offers differ are marked, without saying which is better. Read-only;
// the decision stays with the owner.
export function OwnerCompareOffersPage() {
  const { t, language } = useI18n();
  const { id } = useParams<{ id: string }>();
  const [params] = useSearchParams();
  const ids = params.getAll("ids");
  const query = ids.map((i) => `ids=${encodeURIComponent(i)}`).join("&");
  const { data, error, isPending } = useQuery({
    queryKey: ["owner-compare", id, query],
    queryFn: () => apiFetch<OfferComparison>(`/owner/projects/${id}/offers/compare?${query}`),
    enabled: !!id && ids.length > 0,
    // As the server holds them now: an offer may be revised or withdrawn meanwhile.
    refetchInterval: 60 * 1000,
    refetchOnWindowFocus: true,
  });
  const c = "compareOffers";
  const back = (
    <Link to={`/owner/projects/${id}`} className="font-mono text-xs text-blue underline">
      ← {t("ownerOffer.back")}
    </Link>
  );
  const shell = (body: ReactNode) => <div className="max-w-6xl mx-auto px-4 py-8 grid gap-4">{back}{body}</div>;

  if (ids.length < 2) return shell(<p className="text-sm text-steel">{t(`${c}.needTwo`)}</p>);
  if (isPending) return <PageLoading />;
  if (error || !data) {
    const sealed = error instanceof ApiError && error.status === 404;
    return shell(<p role="alert" className="text-sm text-steel">{sealed ? t(`${c}.sealed`) : t(`${c}.loadError`)}</p>);
  }

  const { requirement: req, offers } = data;
  const none = <span className="text-steel-light">{t("offerPreview.notProvided")}</span>;
  const text = (v: string | null | undefined) => (v ? <p dir="auto" className="whitespace-pre-wrap break-words">{v}</p> : none);
  const timing = (o: Offer) => (
    <>
      <div>
        {t("timing.start")}: {o.proposed_start_date ? fullDate(o.proposed_start_date, language, false) : "—"}
        {" · "}
        {o.proposed_duration_days
          ? `${t("timing.duration")}: ${o.proposed_duration_days} ${t("timing.days")}`
          : `${t("timing.completion")}: ${o.proposed_completion_date ? fullDate(o.proposed_completion_date, language, false) : "—"}`}
      </div>
      {o.timeline_estimate && <div dir="auto">{t("response.completionPeriod")}: {o.timeline_estimate}</div>}
      {o.timing_conflicts?.map((code) => <div key={code} className="text-amber-dark">⚠ {t(`timing.ownerConflict_${code}`)}</div>)}
    </>
  );
  // A row: its label, each offer's cell, and the plain value used only to see whether they differ.
  const rows: { key: string; label: string; cell: (o: Offer) => ReactNode; value: (o: Offer) => string }[] = [
    { key: "status", label: t(`${c}.status`), cell: (o) => (o.status === "submitted" ? t("owner.projectDetail.offerReceived") : t(`feed.offer_${o.status}`)), value: (o) => o.status },
    {
      key: "answered", label: t(`${c}.answered`),
      cell: (o) => (
        <>
          {t("versions.version").replace("{n}", String(o.based_on_material_revision ?? 0))}
          {(o.based_on_material_revision ?? 0) < req.material_revision && <div className="text-amber-dark">⚠ {t("offerPreview.outdated")}</div>}
        </>
      ),
      value: (o) => String(o.based_on_material_revision ?? 0),
    },
    // Stage 6.12: the owner's own marker -- not a ranking.
    { key: "shortlisted", label: t("shortlist.row"), cell: (o) => (o.shortlisted ? `★ ${t("shortlist.badge")}` : "—"), value: () => "" },
    { key: "submitted", label: t("owner.projectDetail.submittedOn"), cell: (o) => (o.submitted_at ? fullDate(o.submitted_at, language) : "—"), value: () => "" },
    { key: "total", label: t(`${c}.total`), cell: (o) => <span className="font-mono font-semibold text-navy">{money(o.amount, req.currency)}</span>, value: (o) => String(o.amount) },
    ...(req.pricing_basis === "per_item"
      ? req.items.map((item) => ({
          key: `item-${item.id}`,
          label: `${item.position}. ${item.description}${item.quantity != null ? ` (${Number(item.quantity)} ${item.unit ?? ""})` : ""}`,
          cell: (o: Offer) => {
            const line = o.item_prices?.find((l) => l.item_id === item.id);
            return line ? <span className="font-mono">{line.rate} → {money(line.line_total, req.currency)}</span> : none;
          },
          value: (o: Offer) => JSON.stringify(o.item_prices?.find((l) => l.item_id === item.id) ?? null),
        }))
      : []),
    // Stage 6.9: what the requirement expects, beside every commitment.
    { key: "timing", label: [t(`${c}.timing`), formatWorkTiming(t, req) && `${t("timing.requirementExpects")} ${formatWorkTiming(t, req)}`].filter(Boolean).join(" — "), cell: timing, value: (o) => [o.proposed_start_date, o.proposed_completion_date, o.proposed_duration_days, o.timeline_estimate].join("|") },
    { key: "approach", label: t(`${c}.approach`), cell: (o) => text(o.message), value: (o) => o.message ?? "" },
    { key: "assumptions", label: t(`${c}.assumptions`), cell: (o) => text(o.assumptions), value: (o) => o.assumptions ?? "" },
    ...req.requested_documents.map((d) => ({
      key: `doc-${d.name}`,
      label: `${t(`${c}.documents`)}: ${d.name}${d.required ? " *" : ""}`,
      cell: (o: Offer) => {
        const doc = o.documents?.find((x) => x.label === d.name);
        return doc ? <a href={doc.url ?? undefined} target="_blank" rel="noreferrer" className="text-blue underline">{doc.file_name}</a> : none;
      },
      value: (o: Offer) => (o.documents?.some((x) => x.label === d.name) ? "1" : "0"),
    })),
    ...req.declarations.map((d) => ({
      key: `decl-${d}`,
      label: `${t(`${c}.declarations`)}: ${d}`,
      cell: (o: Offer) => ((o.declarations_accepted ?? []).includes(d) ? "✓" : "✗"),
      value: (o: Offer) => ((o.declarations_accepted ?? []).includes(d) ? "1" : "0"),
    })),
  ];
  const versions = new Set(offers.map((o) => o.based_on_material_revision ?? 0));

  return shell(
    <>
      <div>
        <h1 className="font-display text-xl text-navy">{t(`${c}.heading`)}</h1>
        <p dir="auto" className="font-display font-semibold text-navy mt-1">{req.title}</p>
        <p className="text-xs text-steel">
          {t("offerPreview.version")} {req.material_revision} · {t(`feed.${req.pricing_basis}`)} · {req.currency}
        </p>
        <p className="text-xs text-steel mt-2">{t(`${c}.intro`)} {t(`${c}.noScore`)}</p>
      </div>
      {data.unavailable.length > 0 && (
        <p className="text-xs text-amber-dark" data-testid="compare-unavailable">{t(`${c}.unavailable`).replace("{n}", String(data.unavailable.length))}</p>
      )}
      {versions.size > 1 && (
        <p className="text-xs text-amber-dark" data-testid="compare-mixed-versions">
          ⚠ {t("owner.projectDetail.mixedVersions").replace("{versions}", [...versions].sort((a, b) => a - b).map((v) => t("versions.version").replace("{n}", String(v))).join(", "))}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs" data-testid="compare-table">
          <thead>
            <tr>
              <th className="text-start border-b-2 border-navy py-2 px-2.5 font-mono text-[10px] uppercase text-steel">{t(`${c}.provider`)}</th>
              {offers.map((o) => (
                <th key={o.id} className="text-start border-b-2 border-navy py-2 px-2.5 align-top">
                  <Link to={`/owner/projects/${id}/offers/${o.id}`} dir="auto" className="font-display font-semibold text-[13px] text-navy underline">
                    {o.service_provider_company_name ?? t("owner.projectDetail.serviceProviderCol")}
                  </Link>
                  {/* Stage 8.14: its track record, for information -- the columns stay in the order chosen. */}
                  <TrackRecord offer={o} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const differs = offers.length > 1 && new Set(offers.map(row.value)).size > 1;
              return (
                <tr key={row.key} className="border-b border-border align-top" data-testid={`compare-row-${row.key}`}>
                  <th scope="row" className="text-start py-2 px-2.5 font-normal text-steel max-w-[14rem]">
                    <span dir="auto">{row.label}</span>
                    {differs && <span className="ms-1 font-mono text-amber-dark" title={t(`${c}.differs`)} data-testid="compare-differs">≠</span>}
                  </th>
                  {offers.map((o) => (
                    <td key={o.id} className="py-2 px-2.5 min-w-[12rem]">{row.cell(o)}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>,
  );
}
