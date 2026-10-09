import { useI18n } from "@/i18n/I18nContext";

// Distinguishes "the list really is empty" from "the request failed" —
// without this, a failed fetch and an empty result render identically,
// which reads as "nothing here" when the real problem is a broken request.
export function QueryError({ onRetry }: { onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="border border-dashed border-red rounded p-10 text-center text-sm text-red bg-red-tint">
      {t("common.loadFailed")}
      <button type="button" onClick={onRetry} className="block mx-auto mt-2 text-xs underline">
        {t("common.retry")}
      </button>
    </div>
  );
}
