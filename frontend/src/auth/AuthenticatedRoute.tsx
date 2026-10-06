import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { PageLoading } from "@/components/PageLoading";

// Looser than ProtectedRoute: any signed-in role may pass, no role match or
// service provider gate required. Used for account-level pages (change password)
// that make sense identically for every role.
export function AuthenticatedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <PageLoading />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
