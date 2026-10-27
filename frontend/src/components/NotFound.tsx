import { Link } from "react-router-dom";
import { ApiError } from "@/api/client";
import { PageLoading } from "@/components/PageLoading";
import { QueryError } from "@/components/QueryError";
import { useAuth } from "@/auth/AuthContext";
import { useI18n } from "@/i18n/I18nContext";

// Where "back to safety" is for whoever is looking: their dashboard, or the
// home page when signed out.
export function homeFor(role: string | undefined): string {
  return role === "owner" ? "/owner/dashboard" : role === "service_provider" ? "/service-provider/dashboard" : role === "admin" ? "/admin/overview" : "/";
}

// What a missing page or record shows instead of a blank screen or an endless
// "Loading…": what happened, and a way back.
export function NotFoundNotice() {
  const { t } = useI18n();
  const { user } = useAuth();
  return (
    <div className="max-w-xl mx-auto my-10 bg-white border border-border rounded px-6 py-6 text-center" data-testid="not-found">
      <h1 className="font-display text-xl font-semibold text-navy mb-2">{t("common.notFoundTitle")}</h1>
      <p className="text-sm text-steel mb-4">{t("common.notFoundBody")}</p>
      <Link to={homeFor(user?.role)} className="inline-block bg-navy hover:bg-navy-deep text-white text-sm font-semibold rounded px-4 py-2">
        {user ? t("common.toDashboard") : t("common.toHome")}
      </Link>
    </div>
  );
}

// An address the app doesn't know: the same notice, on its own page.
export function NotFoundPage() {
  return (
    <main className="min-h-screen px-5 py-10">
      <Link to="/" className="flex items-center justify-center gap-2.5 mb-4">
        <span className="w-8 h-8 border-2 border-navy flex items-center justify-center font-display font-bold text-navy">U</span>
        <span className="font-display font-bold text-navy tracking-wide">U-TENDER</span>
      </Link>
      <NotFoundNotice />
    </main>
  );
}

// A record page while its record loads: loading, gone (not found or not
// shared -- said, with a way back), or a failed request (retry).
export function RecordPending({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (!error) return <PageLoading />;
  if (error instanceof ApiError && (error.status === 404 || error.status === 403)) return <NotFoundNotice />;
  return (
    <main className="max-w-xl mx-auto px-5 py-10">
      <QueryError onRetry={onRetry} />
    </main>
  );
}
