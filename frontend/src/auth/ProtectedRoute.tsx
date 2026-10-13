import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useAuth, type UserRole } from "@/auth/AuthContext";
import { PageLoading } from "@/components/PageLoading";

interface VerificationGatedProfile {
  verification_status: string;
  is_suspended: boolean;
}

// Mirrors src/middleware.ts: must be logged in, must have the matching
// role, and — for gated paths (service provider feed/subscribe/offer, owner
// dashboard/project pages) — must currently be an approved, non-suspended
// account. Re-checked on every route entry rather than cached, since an
// admin can flip either flag at any time. Owners and service providers share
// the identical document-verification shape (ServiceProviderProfile and
// OwnerProfile both expose verification_status/is_suspended), so one gate
// implementation covers both — only the profile endpoint and the
// not-yet-approved redirect target differ.
const GATE_CONFIG: Partial<Record<UserRole, { endpoint: string; statusPath: string }>> = {
  service_provider: { endpoint: "/service-provider/profile", statusPath: "/service-provider/status" },
  owner: { endpoint: "/owner/profile", statusPath: "/owner/status" },
};

// gate="job": the page of a requirement and its transaction. Batch A: a live
// job continues while the account's documents are re-reviewed (changes
// requested, pending review), and a suspended owner keeps read-only access
// (Stage 7.14) -- the server decides what each may see and do there. Only a
// rejected account, or a suspended provider (the server hides the job from
// it), is sent to the status page.
function passesGate(role: UserRole, gate: true | "job", profile: VerificationGatedProfile): boolean {
  if (gate === "job") {
    if (profile.verification_status === "rejected") return false;
    return !(profile.is_suspended && role === "service_provider");
  }
  return profile.verification_status === "approved" && !profile.is_suspended;
}

export function ProtectedRoute({
  role,
  gate = false,
  children,
}: {
  role: UserRole;
  gate?: boolean | "job";
  children: ReactNode;
}) {
  const { user, loading } = useAuth();
  const config = GATE_CONFIG[role];

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["verification-gate-profile", role],
    queryFn: () => apiFetch<VerificationGatedProfile>(config!.endpoint),
    enabled: !!gate && !!user && user.role === role && !!config,
  });

  if (loading) return <PageLoading />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to="/" replace />;

  if (gate && config) {
    if (profileLoading) return <PageLoading />;
    if (!profile || !passesGate(role, gate, profile)) {
      return <Navigate to={config.statusPath} replace />;
    }
  }

  return <>{children}</>;
}

// Whether the account is approved and active right now (the gate's own
// query, so usually already loaded). Pages reachable under gate="job" use it
// to hold back what the server allows only an approved account -- a review.
export function useAccountApproved(role: "owner" | "service_provider"): boolean | undefined {
  const config = GATE_CONFIG[role]!;
  const { data } = useQuery({
    queryKey: ["verification-gate-profile", role],
    queryFn: () => apiFetch<VerificationGatedProfile>(config.endpoint),
  });
  return data ? data.verification_status === "approved" && !data.is_suspended : undefined;
}
