import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ContractorProfile } from "@/api/types";
import { stars } from "@/lib/format";
import { QueryError } from "@/components/QueryError";

function statusBadge(status: string) {
  switch (status) {
    case "approved":
      return "bg-green-tint text-green";
    case "changes_requested":
      return "bg-red-tint text-red";
    case "pending_review":
      return "bg-amber/15 text-amber-dark";
    default:
      return "bg-blue-tint text-steel";
  }
}

const MARKETPLACE_BADGE: Record<string, string> = {
  documents_incomplete: "bg-blue-tint text-steel",
  submitted_for_review: "bg-amber/15 text-amber-dark",
  changes_requested: "bg-red-tint text-red",
  payment_required: "bg-amber/15 text-amber-dark",
  payment_restricted: "bg-red-tint text-red",
  verified_active: "bg-green-tint text-green",
  suspended: "bg-red-tint text-red",
};

export function AdminContractorsPage() {
  const {
    data: contractors,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["admin-contractors"],
    queryFn: () => apiFetch<ContractorProfile[]>("/admin/contractors"),
  });

  return (
    <main className="max-w-5xl mx-auto px-5 py-8">
      <div className="mb-6">
        <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">Admin · Service providers</span>
        <h1 className="font-display text-2xl font-semibold text-navy mb-1">All service providers</h1>
        <p className="text-[13.5px] text-steel">{contractors?.length ?? 0} total. Edit details, change verification status, suspend, or delete.</p>
      </div>

      {isError ? (
        <QueryError onRetry={() => refetch()} />
      ) : !contractors?.length ? (
        <div className="border border-dashed border-border rounded p-10 text-center text-sm text-steel">No service providers have signed up yet.</div>
      ) : (
        <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">Company</th>
              <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">Status</th>
              <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">Marketplace access</th>
              <th className="font-mono text-[10px] uppercase tracking-wide text-steel text-left border-b-2 border-navy py-2 px-2.5">Rating</th>
              <th className="border-b-2 border-navy py-2 px-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {contractors.map((c) => (
              <tr key={c.user_id} className="border-b border-border">
                <td className="py-3 px-2.5">
                  <div className="font-display font-semibold text-[13.5px]">{c.company_name}</div>
                  <div className="text-[11.5px] text-steel-light">{c.primary_trade || "Trade not set"}</div>
                </td>
                <td className="py-3 px-2.5">
                  <div className="flex flex-col gap-1 items-start">
                    <span className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded-full ${statusBadge(c.verification_status)}`}>
                      {c.verification_status.replace("_", " ")}
                    </span>
                    {c.is_suspended && <span className="font-mono text-[10px] uppercase px-2 py-0.5 rounded-full bg-red-tint text-red">Suspended</span>}
                  </div>
                </td>
                <td className="py-3 px-2.5">
                  <span className={`font-mono text-[10px] uppercase px-2 py-0.5 rounded-full ${MARKETPLACE_BADGE[c.marketplace_status] ?? "bg-blue-tint text-steel"}`}>
                    {c.marketplace_status.replace(/_/g, " ")}
                  </span>
                  {c.payment_override_active && (
                    <span className="block font-mono text-[10px] text-blue mt-1">via admin override</span>
                  )}
                </td>
                <td className="py-3 px-2.5">
                  <span className="text-amber text-[11px]">{stars(Number(c.avg_rating))}</span>{" "}
                  <span className="font-mono text-[11px] text-steel">({c.review_count})</span>
                </td>
                <td className="py-3 px-2.5">
                  <Link
                    to={`/admin/contractors/${c.user_id}`}
                    className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-3 py-1.5"
                  >
                    Manage
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </main>
  );
}
