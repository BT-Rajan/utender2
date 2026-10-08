import { Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { OwnerDocument, OwnerProfile } from "@/api/types";
import { PageLoading } from "@/components/PageLoading";
import { useI18n } from "@/i18n/I18nContext";
import { VerificationStateBanner } from "@/components/VerificationChecklist";

function statusBadge(status: string) {
  switch (status) {
    case "approved":
      return "bg-green-tint text-green";
    case "rejected":
      return "bg-red-tint text-red";
    case "pending":
      return "bg-amber/15 text-amber-dark";
    default:
      return "bg-blue-tint text-steel";
  }
}

export function OwnerStatusPage() {
  const { t } = useI18n();
  const { data: profile } = useQuery({
    queryKey: ["owner-profile"],
    queryFn: () => apiFetch<OwnerProfile>("/owner/profile"),
  });
  const { data: docs } = useQuery({
    queryKey: ["owner-documents"],
    queryFn: () => apiFetch<OwnerDocument[]>("/owner/documents"),
    enabled: !!profile,
  });

  if (!profile) return <PageLoading />;

  // Nothing submitted yet: the next step is the verification form itself
  // (who the account represents, the documents, "Submit for review") -- not
  // a status that would say it is under review.
  if (profile.verification_status === "incomplete") return <Navigate to="/owner/verify" replace />;

  if (profile.is_suspended) {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8">
        <div className="bg-white border border-red border-l-4 rounded px-5 py-4">
          <div className="font-display font-semibold text-navy">{t("owner.status.suspendedTitle")}</div>
          <p className="text-sm text-steel mt-1.5">{t("owner.status.suspendedBody")}</p>
        </div>
      </main>
    );
  }

  if (profile.verification_status === "approved") {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8">
        <div className="bg-white border border-green border-l-4 rounded px-5 py-4">
          <div className="font-display font-semibold text-navy">{t("owner.status.approvedTitle")}</div>
          <p className="text-sm text-steel mt-1.5">{t("owner.status.approvedBody")}</p>
          <Link to="/owner/dashboard" className="inline-block mt-3 bg-navy hover:bg-navy-deep text-white text-xs font-semibold rounded px-4 py-2">
            {t("owner.status.dashboardLink")}
          </Link>
        </div>
      </main>
    );
  }

  // A final rejection (or any reviewer message) is shown as-is, with the reason.
  if (profile.verification_status === "rejected") {
    return (
      <main className="max-w-2xl mx-auto px-5 py-8">
        <VerificationStateBanner state={profile.verification_state} note={profile.verification_note} />
      </main>
    );
  }

  const bannerClasses = profile.verification_status === "changes_requested" ? "border-red" : "border-amber";
  const bannerTitle =
    profile.verification_status === "changes_requested"
      ? t("owner.status.changesRequestedTitle")
      : t("owner.status.underReviewTitle");

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("owner.status.eyebrow")}</span>
      <h1 className="font-display text-2xl font-semibold text-navy mb-1">{t("owner.status.heading")}</h1>
      <p className="text-[13.5px] text-steel mb-6">{profile.full_name}</p>
      {profile.verification_note && (
        <VerificationStateBanner state={profile.verification_state} note={profile.verification_note} />
      )}

      <div className={`bg-white border border-l-4 rounded px-5 py-4 mb-6 flex items-center justify-between flex-wrap gap-3 ${bannerClasses}`}>
        <div>
          <div className="font-display font-semibold text-navy text-sm">{bannerTitle}</div>
          <div className="font-mono text-[11px] text-steel mt-1">
            {t("owner.status.submittedOn")} {new Date(profile.created_at).toLocaleDateString()}
          </div>
        </div>
        <span className={`font-mono text-[10px] uppercase px-2.5 py-1 rounded-full ${statusBadge(profile.verification_status === "pending_review" ? "pending" : "rejected")}`}>
          {profile.verification_status === "pending_review" ? t("owner.status.pending") : t("owner.status.actionNeeded")}
        </span>
      </div>

      <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2">{t("owner.status.document")}</th>
            <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2">{t("owner.status.statusCol")}</th>
            <th className="border-b-2 border-navy py-2"></th>
          </tr>
        </thead>
        <tbody>
          {docs?.map((d) => (
            <tr key={d.id} className="border-b border-border">
              <td className="py-3.5">
                <div className="font-display font-semibold text-[13.5px]">{d.requirement_name}</div>
                <span className="font-mono text-[9.5px] uppercase text-steel-light">
                  {d.requirement_is_required ? t("owner.status.required") : t("owner.status.optional")}
                </span>
                {d.status === "rejected" && d.admin_note && (
                  <div className="mt-1.5 text-[11.5px] text-red bg-red-tint px-2.5 py-1.5 rounded font-mono">
                    {t("owner.status.adminNote")} {d.admin_note}
                  </div>
                )}
              </td>
              <td className="py-3.5">
                <span className={`font-mono text-[10px] uppercase px-2 py-1 rounded-full ${statusBadge(d.status)}`}>{d.status.replace("_", " ")}</span>
              </td>
              <td className="py-3.5">
                {(d.status === "not_submitted" || d.status === "rejected") && (
                  <a href="/owner/verify" className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-3 py-1.5">
                    {d.status === "rejected" ? t("owner.status.reupload") : t("owner.status.upload")}
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      <p className="text-xs text-steel-light mt-4">{t("owner.status.footerNote")}</p>
    </main>
  );
}
