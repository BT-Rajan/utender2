import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";

export function DeleteServiceProviderForm({
  serviceProviderId,
  companyName,
  onDeleted,
}: {
  serviceProviderId: string;
  companyName: string;
  onDeleted: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: () => apiFetch(`/admin/service-providers/${serviceProviderId}`, { method: "DELETE" }),
    onSuccess: onDeleted,
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not delete this service provider."),
  });

  if (!confirming) {
    return (
      <button type="button" onClick={() => setConfirming(true)} className="text-xs text-red underline">
        Delete service provider permanently
      </button>
    );
  }

  return (
    <div className="bg-red-tint border border-red rounded px-4 py-3.5 max-w-md">
      <p className="text-xs text-red mb-2">
        This permanently deletes the account, its documents, and its offers. Type the company name to confirm.
      </p>
      {error && <p className="text-xs bg-white border border-red rounded px-2.5 py-2 mb-2.5">{error}</p>}
      <input
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        placeholder={companyName}
        className="w-full border border-red rounded px-2.5 py-1.5 text-sm mb-2.5 bg-white"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => deleteMutation.mutate()}
          disabled={typed !== companyName || deleteMutation.isPending}
          className="bg-red disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-semibold rounded px-3 py-1.5"
        >
          {deleteMutation.isPending ? "Deleting…" : "Confirm delete"}
        </button>
        <button
          type="button"
          onClick={() => {
            setConfirming(false);
            setTyped("");
            setError(null);
          }}
          className="text-xs text-steel underline"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
