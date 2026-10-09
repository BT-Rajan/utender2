import type { VerificationState } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";
import { SupportContact } from "@/components/SupportContact";

// The account holder's checklist, built server-side from the admin's
// verification policy for this account's role and stakeholder type
// (GET /owner/documents or /service-provider/documents). Nothing here
// knows which documents exist.

interface ChecklistDocument {
  requirement_id: string;
  requirement_name: string | null;
  requirement_description: string | null;
  requirement_is_required: boolean | null;
  status: "not_submitted" | "pending" | "approved" | "rejected";
  admin_note: string | null;
}

const EDITABLE_STATES: VerificationState[] = ["not_started", "incomplete", "correction_required"];

export function isVerificationEditable(state: VerificationState | undefined): boolean {
  return !!state && EDITABLE_STATES.includes(state);
}

const DOC_TONE: Record<ChecklistDocument["status"], string> = {
  not_submitted: "text-steel",
  pending: "text-amber-dark",
  approved: "text-green",
  rejected: "text-red",
};

export function VerificationStateBanner({ state, note }: { state: VerificationState; note: string | null }) {
  const { t } = useI18n();
  const tone =
    state === "approved" ? "border-green" : state === "rejected" || state === "correction_required" ? "border-red" : "border-amber";
  return (
    <div className={`bg-white border border-l-4 rounded px-4 py-3 mb-6 max-w-xl ${tone}`}>
      <div className="font-mono text-[10px] uppercase tracking-wide text-steel">{t("verification.stateLabel")}</div>
      <div className="font-display font-semibold text-navy">{t(`verification.state_${state}`)}</div>
      {state === "rejected" && <p className="text-sm text-steel mt-1">{t("verification.rejectedBody")}</p>}
      {state === "rejected" && <SupportContact />}
      {note && (
        <p className="text-sm text-navy mt-1">
          <span className="text-steel">{t("verification.reviewerMessage")}</span> {note}
        </p>
      )}
      {!isVerificationEditable(state) && <p className="text-xs text-steel-light mt-1">{t("verification.locked")}</p>}
    </div>
  );
}

export function VerificationChecklist({
  documents,
  editable,
  canUpload,
  onUpload,
  labels,
}: {
  documents: ChecklistDocument[];
  editable: boolean;
  // Per-row override: e.g. optional qualifications a verified account may add later.
  canUpload?: (d: ChecklistDocument) => boolean;
  onUpload: (requirementId: string, file: File) => void;
  labels: { document: string; status: string; required: string; optional: string };
}) {
  const { t } = useI18n();
  if (!documents.length) return <p className="text-sm text-steel">{t("verification.noRequirements")}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-left">
            <th className="font-mono text-[10px] uppercase text-steel border-b-2 border-navy py-2">{labels.document}</th>
            <th className="font-mono text-[10px] uppercase text-steel border-b-2 border-navy py-2">{labels.status}</th>
            <th className="border-b-2 border-navy py-2"></th>
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => (
            <tr key={d.requirement_id} className={`border-b border-border ${d.status === "rejected" ? "bg-red-tint/40" : ""}`}>
              <td className="py-3 pe-3">
                <div className="font-display font-semibold text-sm">{d.requirement_name}</div>
                {d.requirement_description && <div className="text-xs text-steel-light">{d.requirement_description}</div>}
                <span className="font-mono text-[9.5px] uppercase text-steel-light">{d.requirement_is_required ? labels.required : labels.optional}</span>
                {d.status === "rejected" && d.admin_note && (
                  <div className="mt-1.5 text-[12px] text-red">
                    <strong>{t("verification.correctionNeeded")}</strong> {d.admin_note}
                  </div>
                )}
              </td>
              <td className={`py-3 font-mono text-xs capitalize ${DOC_TONE[d.status]}`}>
                {d.status === "rejected" ? t("verification.state_correction_required") : d.status.replace("_", " ")}
              </td>
              <td className="py-3">
                {(editable || canUpload?.(d)) && (
                  <label className="flex items-center gap-2 text-xs">
                    {d.status !== "not_submitted" && <span className="text-steel">{t("verification.replace")}:</span>}
                    <input
                      type="file"
                      aria-label={d.requirement_name ?? undefined}
                      className="text-xs"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) onUpload(d.requirement_id, file);
                        e.target.value = "";
                      }}
                    />
                  </label>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
