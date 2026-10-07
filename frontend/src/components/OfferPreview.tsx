import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { OfferPreview as OfferPreviewData, OfferReadiness, OfferRevisionEntry } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";
import { formatArea } from "@/lib/location";
import { fullDate } from "@/lib/format";
import { money } from "@/lib/money";
import { formatWorkTiming } from "@/lib/dates";

// Stage 5.8/5.9: which part of the form each quality-gate section is about.
export const SECTION_ANCHORS: Record<OfferReadiness["issues"][number]["section"], string | null> = {
  price: "offer-section-price",
  technical: "offer-message",
  timing: "offer-section-timing",
  documents: "offer-section-documents",
  declarations: "offer-section-declarations",
  requirement: null,
  account: null,
  eligibility: null,
  offer: null,
};

// Stage 5.9: the provider's offer exactly as stored -- what submitting would
// send -- read fresh from the server each time it opens (no preview copy),
// beside the requirement as it is now and the quality gate's verdict.
// Nothing here submits, seals or locks the offer.
export function OfferPreview({
  projectId,
  onEdit,
  readOnly = false,
}: {
  projectId: string;
  onEdit?: (section?: string | null) => void;
  // Stage 5.16: the provider's own offer once nothing can change it (offers
  // closed): the same stored record, without the submit checks or editing.
  readOnly?: boolean;
}) {
  const { t, language } = useI18n();
  const { data, isError } = useQuery({
    queryKey: ["offer-preview", projectId],
    queryFn: () => apiFetch<OfferPreviewData>(`/projects/${projectId}/offers/draft/preview`),
    staleTime: 0,
    refetchOnMount: "always",
  });
  if (isError) return <p className="text-sm text-red">{t("offerPreview.unavailable")}</p>;
  if (!data) return <p className="text-sm text-steel">{t("offerPreview.loading")}</p>;
  const { requirement: req, offer, readiness } = data;

  return (
    <div className="grid gap-4" data-testid="offer-preview">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <h2 className="font-display text-lg text-navy">{readOnly ? t("offerHistory.yourOffer") : t("offerPreview.heading")}</h2>
        {!readOnly && onEdit && (
          <button type="button" onClick={() => onEdit()} className="border border-navy text-navy text-sm font-semibold rounded px-4 py-2">
            {t("offerPreview.backToEdit")}
          </button>
        )}
      </div>
      <p className="text-xs text-steel">{readOnly ? t("offerHistory.readOnlyNote") : t("offerPreview.notSubmitted")}</p>

      {/* The quality gate (Stage 5.8): never implies ready when it isn't. */}
      {!readOnly && <div className={`rounded px-4 py-3 text-sm border ${readiness.ready ? "border-green bg-green/5" : "border-amber-dark/40 bg-amber/10"}`} data-testid="preview-readiness">
        <strong className="font-display text-navy">{readiness.ready ? t("offerPreview.passed") : t("readiness.notReady")}</strong>
        {!readiness.ready && (
          <ul className="mt-2 grid gap-1">
            {readiness.issues.map((issue, i) => (
              <li key={i} className="text-steel">
                <span className="font-mono text-[10px] uppercase text-navy me-2">{t(`readiness.section_${issue.section}`)}</span>
                {issue.message}
                {SECTION_ANCHORS[issue.section] && onEdit && (
                  <button type="button" onClick={() => onEdit(SECTION_ANCHORS[issue.section])} className="ms-2 text-xs text-blue underline">
                    {t("offerPreview.fix")}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>}

      <OfferRecord requirement={req} offer={offer} providerName={data.provider_name} onCurrentVersion={data.on_current_version} />
    </div>
  );
}

// Stage 5.9 / 6.4: an offer exactly as stored, beside the requirement it
// answers -- the provider's own preview and the owner's review show the same
// record the same way. Display only: nothing is recalculated or editable.
export function OfferRecord({
  requirement: req,
  offer,
  providerName,
  onCurrentVersion,
  versionNote,
  viewer = "provider",
}: {
  requirement: OfferPreviewData["requirement"];
  offer: OfferPreviewData["offer"];
  providerName: string | null;
  onCurrentVersion: boolean;
  versionNote?: ReactNode;
  // Stage 6.9: whose page this is -- the owner reads about "this offer", not "you".
  viewer?: "owner" | "provider";
}) {
  const { t, language } = useI18n();
  const items = new Map(req.items.map((i) => [i.id, i]));
  const attached = new Map((offer.documents ?? []).map((d) => [d.label, d]));
  const accepted = new Set(offer.declarations_accepted ?? []);
  const none = <span className="text-steel-light">{t("offerPreview.notProvided")}</span>;
  const heading = "font-mono text-[11px] uppercase tracking-wide text-navy mb-1";
  const data = { provider_name: providerName, on_current_version: onCurrentVersion };
  return (
    <>
      <section className="border border-border rounded px-4 py-3" data-testid="preview-requirement">
        <div className={heading}>{t("offerPreview.requirement")}</div>
        <div dir="auto" className="font-display font-semibold text-navy">{req.title}</div>
        <div className="text-xs text-steel">
          {req.trade && `${req.trade} · `}
          {formatArea(t, req.governorate, req.area)} · {t("service_provider.offer.deadlineLabel")} {fullDate(req.bid_deadline, language)}
        </div>
        <div className="text-xs text-steel mt-1">
          {t("offerPreview.version")} {req.material_revision}
          {req.amendment_number != null && ` · ${t("offerPreview.amendment")} ${req.amendment_number}`}
          {" · "}
          {t(`feed.${req.pricing_basis}`)}
          {req.tender_type === "sealed" && ` · ${t("feed.sealed")}`}
        </div>
        {!data.on_current_version && <p className="text-xs text-amber-dark mt-1" data-testid="preview-outdated">⚠ {t("offerPreview.outdated")}</p>}
        {versionNote}
        {req.description && (
          <details className="mt-2 text-xs text-steel">
            <summary className="cursor-pointer text-blue">{t("offerPreview.scope")}</summary>
            <p dir="auto" className="whitespace-pre-wrap break-words mt-1">{req.description}</p>
          </details>
        )}
        {/* Stage 6.8: a single-price requirement's items of work (quantities and
            specifications) -- what the offer's technical response answers. */}
        {req.pricing_basis !== "per_item" && req.items.length > 0 && (
          <details className="mt-2 text-xs text-steel" data-testid="preview-scope-items">
            <summary className="cursor-pointer text-blue">{t("offerPreview.scopeItems")} ({req.items.length})</summary>
            <ol className="mt-1 grid gap-1">
              {req.items.map((item) => (
                <li key={item.id}>
                  {item.position}. {item.description}
                  {item.quantity != null && ` — ${Number(item.quantity)} ${item.unit ?? ""}`}
                  {item.specification && <div dir="auto" className="whitespace-pre-wrap break-words">{item.specification}</div>}
                </li>
              ))}
            </ol>
          </details>
        )}
      </section>

      {data.provider_name && (
        <section className="border border-border rounded px-4 py-3">
          <div className={heading}>{t("offerPreview.from")}</div>
          <div dir="auto" className="text-navy">{data.provider_name}</div>
        </section>
      )}

      <section className="border border-border rounded px-4 py-3" data-testid="preview-price">
        <div className={heading}>{t("readiness.section_price")}</div>
        {req.pricing_basis === "per_item" && (
          <table className="w-full text-xs mb-2">
            <tbody>
              {req.items.map((item) => {
                const line = offer.item_prices?.find((l) => l.item_id === item.id);
                return (
                  <tr key={item.id} className="border-b border-border">
                    <td className="py-1 pe-2">
                      {item.position}. {item.description}
                      {/* Stage 6.8: the item's specification, as the requirement states it. */}
                      {item.specification && <div dir="auto" className="text-steel whitespace-pre-wrap break-words">{item.specification}</div>}
                    </td>
                    <td className="py-1 pe-2 font-mono text-end whitespace-nowrap">
                      {line ? (item.quantity != null ? `${Number(item.quantity)} ${item.unit ?? ""} × ${line.rate}` : line.rate) : "—"}
                    </td>
                    <td className="py-1 font-mono text-end whitespace-nowrap">{line ? money(line.line_total, req.currency) : none}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        <div className="font-mono text-navy text-base" data-testid="preview-total">
          {t("offerPreview.total")} {offer.amount ? money(offer.amount, req.currency) : "—"}
        </div>
        {/* only the lines that belong to this requirement's items */}
        {offer.item_prices?.some((l) => !items.has(l.item_id)) && <p className="text-xs text-red">{t("offerPreview.unknownItems")}</p>}
      </section>

      <section className="border border-border rounded px-4 py-3" data-testid="preview-technical">
        <div className={heading}>
          {t("response.approach")}
          {req.approach && <span className="normal-case text-steel"> · {t(`response.${req.approach}`)}</span>}
        </div>
        {offer.message ? <p dir="auto" className="text-sm whitespace-pre-wrap break-words">{offer.message}</p> : none}
      </section>

      <section className="border border-border rounded px-4 py-3" data-testid="preview-timing">
        <div className={heading}>{viewer === "owner" ? t("timing.ownerHeading") : t("timing.heading")}</div>
        <div className="text-sm">
          {t("timing.start")}: {offer.proposed_start_date ? fullDate(offer.proposed_start_date, language, false) : none}
          {" · "}
          {offer.proposed_duration_days
            ? `${t("timing.duration")}: ${offer.proposed_duration_days} ${t("timing.days")}`
            : <>{t("timing.completion")}: {offer.proposed_completion_date ? fullDate(offer.proposed_completion_date, language, false) : none}</>}
        </div>
        {(offer.timeline_estimate || req.completion_period === "required") && (
          <p dir="auto" className="text-sm mt-1">
            {t("response.completionPeriod")}
            {req.completion_period && <span className="text-steel"> ({t(`response.${req.completion_period}`)})</span>}: {offer.timeline_estimate || none}
          </p>
        )}
        {/* Stage 6.9: beside the commitment, what the requirement expects (Stage 3.7). */}
        {formatWorkTiming(t, req) && (
          <p className="text-xs text-steel mt-1" data-testid="preview-timing-expected">
            {viewer === "owner" ? t("timing.requirementExpects") : t("timing.ownerExpects")} {formatWorkTiming(t, req)}
          </p>
        )}
        {offer.timing_conflicts?.map((code) => (
          <p key={code} className="text-xs text-amber-dark">⚠ {t(viewer === "owner" ? `timing.ownerConflict_${code}` : `timing.conflict_${code}`)}</p>
        ))}
      </section>

      <section className="border border-border rounded px-4 py-3" data-testid="preview-assumptions">
        <div className={heading}>{t("response.assumptions")}</div>
        {offer.assumptions ? <p dir="auto" className="text-sm whitespace-pre-wrap break-words">{offer.assumptions}</p> : none}
      </section>

      {(req.requested_documents.length > 0 || (offer.documents?.length ?? 0) > 0) && (
        <section className="border border-border rounded px-4 py-3" data-testid="preview-documents">
          <div className={heading}>{t("response.attachments")}</div>
          <ul className="text-sm grid gap-1">
            {req.requested_documents.map((d) => {
              const doc = attached.get(d.name);
              return (
                <li key={d.name}>
                  {d.name}
                  {d.required && <span className="text-amber-dark"> *</span>}:{" "}
                  {doc ? (
                    <a href={doc.url ?? undefined} target="_blank" rel="noreferrer" className="text-blue underline">{doc.file_name}</a>
                  ) : (
                    none
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {req.declarations.length > 0 && (
        <section className="border border-border rounded px-4 py-3" data-testid="preview-declarations">
          <div className={heading}>{t("response.declarations")}</div>
          <ul className="text-sm grid gap-1">
            {req.declarations.map((d) => (
              <li key={d} dir="auto">{accepted.has(d) ? "✓" : "✗"} {d}</li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

// Stage 5.16: the provider's earlier versions of this offer, as submitted
// (Stage 5.13 history) -- what changed, when, and the requirement version
// each answered. Their own offer only; nothing of anyone else's.
export function OfferHistory({ projectId, currency, offerId }: { projectId: string; currency: string; offerId?: string }) {
  const { t, language } = useI18n();
  // Stage 6.4: the owner reads the same history of an offer on their requirement.
  const url = offerId ? `/owner/projects/${projectId}/offers/${offerId}/history` : `/projects/${projectId}/offers/mine/history`;
  const { data: history } = useQuery({
    queryKey: offerId ? ["owner-offer-history", projectId, offerId] : ["my-offer-history", projectId],
    queryFn: () => apiFetch<OfferRevisionEntry[]>(url),
  });
  if (!history?.length) return null;
  return (
    <details className="border border-border rounded px-4 py-3 mt-4 text-sm" data-testid="offer-history">
      <summary className="cursor-pointer font-mono text-[11px] uppercase tracking-wide text-navy">
        {t("offerHistory.earlier")} ({history.length})
      </summary>
      <ol className="mt-2 grid gap-2">
        {[...history].reverse().map((h) => (
          <li key={h.id} className="border-t border-border pt-2">
            <div className="font-mono text-xs text-navy">
              {t("submitOffer.revision")} {h.revision_number} · {h.status === "submitted" ? t("service_provider.feed.bidPlaced") : t(`feed.offer_${h.status}`)}
              {h.submitted_at && ` · ${fullDate(h.submitted_at, language)}`} · {t("offerPreview.version")} {h.based_on_material_revision}
            </div>
            <div className="text-xs text-steel">
              {money(h.amount, currency)}
              {h.proposed_duration_days ? ` · ${h.proposed_duration_days} ${t("timing.days")}` : ""}
              {h.documents?.length ? ` · ${h.documents.map((d) => d.file_name).join(", ")}` : ""}
            </div>
            {h.message && <p dir="auto" className="text-xs text-steel whitespace-pre-wrap break-words mt-0.5">{h.message}</p>}
          </li>
        ))}
      </ol>
    </details>
  );
}
