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

export function ProtectedRoute({
  role,
  gate = false,
  children,
}: {
  role: UserRole;
  gate?: boolean;
  children: ReactNode;
}) {
  const { user, loading } = useAuth();
  const config = GATE_CONFIG[role];

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["verification-gate-profile", role],
    queryFn: () => apiFetch<VerificationGatedProfile>(config!.endpoint),
    enabled: gate && !!user && user.role === role && !!config,
  });

  if (loading) return <PageLoading />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== role) return <Navigate to="/" replace />;

  if (gate && config) {
    if (profileLoading) return <PageLoading />;
    if (!profile || profile.verification_status !== "approved" || profile.is_suspended) {
      return <Navigate to={config.statusPath} replace />;
    }
  }

  return <>{children}</>;
}
