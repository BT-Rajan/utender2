import { useState } from "react";

// Admin review controls shared by the service provider queue and the owner
// detail page. The backend enforces every rule shown here (a correction
// needs a note, an expiry-bearing requirement needs a date, a rejection
// needs a reason); the UI only asks for them up front.

export interface DocumentDecision {
  decision: "approved" | "rejected";
  note?: string;
  expires_on?: string;
}

export function DocumentDecisionControls({
  requiresExpiry,
  pending,
  onDecide,
}: {
  requiresExpiry: boolean;
  pending: boolean;
  onDecide: (d: DocumentDecision) => void;
}) {
  const [mode, setMode] = useState<"idle" | "approve" | "correct">("idle");
  const [note, setNote] = useState("");
  const [expiresOn, setExpiresOn] = useState("");

  if (mode === "correct") {
    return (
      <form
        className="grid gap-1.5 w-64"
        onSubmit={(e) => {
          e.preventDefault();
          onDecide({ decision: "rejected", note });
        }}
      >
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          required
          rows={2}
          placeholder="What needs to be corrected?"
          className="border border-border rounded px-2 py-1.5 text-xs"
        />
        <div className="flex gap-2">
          <button type="submit" disabled={pending || !note.trim()} className="bg-red-tint text-red text-xs font-semibold rounded px-3 py-1.5">
            Request correction
          </button>
          <button type="button" onClick={() => setMode("idle")} className="text-xs text-steel underline">
            Cancel
          </button>
        </div>
      </form>
    );
  }

  if (mode === "approve" && requiresExpiry) {
    return (
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          onDecide({ decision: "approved", expires_on: expiresOn });
        }}
      >
        <label className="font-mono text-[10px] text-steel">
          Expires on
          <input type="date" value={expiresOn} onChange={(e) => setExpiresOn(e.target.value)} required className="ms-1 border border-border rounded px-1.5 py-1 text-xs" />
        </label>
        <button type="submit" disabled={pending || !expiresOn} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5">
          Approve
        </button>
        <button type="button" onClick={() => setMode("idle")} className="text-xs text-steel underline">
          Cancel
        </button>
      </form>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        disabled={pending}
        onClick={() => (requiresExpiry ? setMode("approve") : onDecide({ decision: "approved" }))}
        className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-3 py-1.5"
      >
        Approve
      </button>
      <button type="button" disabled={pending} onClick={() => setMode("correct")} className="bg-red-tint text-red text-xs font-semibold rounded px-3 py-1.5">
        Request correction
      </button>
    </div>
  );
}

export function ApplicationDecisionControls({
  canApprove,
  pending,
  onApprove,
  onRequestChanges,
  onReject,
}: {
  canApprove: boolean;
  pending: boolean;
  onApprove: () => void;
  onRequestChanges: (note: string) => void;
  onReject: (reason: string) => void;
}) {
  const [mode, setMode] = useState<"idle" | "changes" | "reject">("idle");
  const [text, setText] = useState("");

  if (mode !== "idle") {
    const rejecting = mode === "reject";
    return (
      <form
        className="grid gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (rejecting) onReject(text);
          else onRequestChanges(text);
        }}
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          required={rejecting}
          rows={3}
          placeholder={rejecting ? "Reason for rejecting this application (shown to the applicant)" : "What should the applicant change? (optional when a document is already flagged)"}
          className="border border-border rounded px-3 py-2 text-sm"
        />
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={pending || (rejecting && !text.trim())}
            className={rejecting ? "bg-red text-white text-sm font-semibold rounded px-4 py-2" : "border border-navy text-navy text-sm font-semibold rounded px-4 py-2"}
          >
            {rejecting ? "Reject application" : "Request changes"}
          </button>
          <button type="button" onClick={() => setMode("idle")} className="text-xs text-steel underline">
            Cancel
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex flex-wrap gap-3">
      <button
        type="button"
        onClick={onApprove}
        disabled={pending || !canApprove}
        className="bg-green hover:opacity-90 disabled:opacity-50 text-white text-sm font-semibold rounded px-4 py-2"
      >
        Approve application
      </button>
      <button type="button" onClick={() => setMode("changes")} disabled={pending} className="border border-navy text-navy text-sm font-semibold rounded px-4 py-2">
        Request changes
      </button>
      <button type="button" onClick={() => setMode("reject")} disabled={pending} className="bg-red-tint text-red text-sm font-semibold rounded px-4 py-2">
        Reject application
      </button>
    </div>
  );
}
