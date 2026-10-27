import { useState } from "react";
import { useI18n } from "@/i18n/I18nContext";

export function RatingInput({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  const { t } = useI18n();
  const [hover, setHover] = useState(0);

  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          onMouseEnter={() => setHover(n)}
          onMouseLeave={() => setHover(0)}
          className="text-2xl leading-none"
          aria-label={t("ownerReview.rating").replace("{n}", String(n))}  // in the page's language
          aria-pressed={value === n}
        >
          <span className={(hover || value) >= n ? "text-amber" : "text-border"}>★</span>
        </button>
      ))}
    </div>
  );
}
