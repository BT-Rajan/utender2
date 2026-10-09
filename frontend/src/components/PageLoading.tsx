import { useI18n } from "@/i18n/I18nContext";

// A minimal loading state for the gap between route entry and first data
// fetch. The original app rendered server-side, so this gap didn't exist
// there — a blank `return null` here would just flash an empty page.
export function PageLoading() {
  const { t } = useI18n();
  return <div className="max-w-5xl mx-auto px-5 py-16 text-center text-sm text-steel">{t("common.loading")}</div>;
}
