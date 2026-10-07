import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n } from "@/i18n/I18nContext";

export interface ConfirmOptions {
  title: string;
  body?: string;
  confirmLabel: string;
  tone?: "default" | "danger";
}

type Confirm = (options: ConfirmOptions) => Promise<boolean>;
const ConfirmContext = createContext<Confirm | null>(null);

// The app's own confirmation step for consequential actions (publishing,
// discarding, removing): states what will happen, in the interface's
// language and direction, with Cancel focused first so a stray Enter or
// click never confirms. Escape or clicking outside cancels.
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const { t, dir } = useI18n();
  const [pending, setPending] = useState<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  const confirm = useCallback<Confirm>((options) => new Promise((resolve) => setPending({ ...options, resolve })), []);
  const close = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
  };

  useEffect(() => {
    if (!pending) return;
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {pending && (
        <div className="fixed inset-0 z-50 bg-navy/50 flex items-center justify-center px-4" onMouseDown={() => close(false)}>
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            aria-describedby={pending.body ? "confirm-body" : undefined}
            dir={dir}
            className="bg-white rounded shadow-lg max-w-md w-full px-6 py-5"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <h2 id="confirm-title" className="font-display text-lg font-semibold text-navy mb-2">
              {pending.title}
            </h2>
            {pending.body && (
              <p id="confirm-body" className="text-sm text-steel whitespace-pre-line mb-5">
                {pending.body}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button ref={cancelRef} type="button" onClick={() => close(false)} className="border border-border text-steel text-sm font-semibold rounded px-4 py-2">
                {t("confirm.cancel")}
              </button>
              <button
                type="button"
                onClick={() => close(true)}
                className={`text-white text-sm font-semibold rounded px-4 py-2 ${pending.tone === "danger" ? "bg-red hover:opacity-90" : "bg-navy hover:bg-navy-deep"}`}
              >
                {pending.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): Confirm {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm must be used inside ConfirmProvider");
  return confirm;
}
