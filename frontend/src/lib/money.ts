// Stage 3.8: every price in U-Tender is in the marketplace currency (backend
// setting marketplace_currency, returned on each requirement as `currency`).
// This default mirrors it for lists that don't carry a requirement.
export const MARKETPLACE_CURRENCY = "KWD";

// "KWD 1,578.625" -- Intl knows KWD has three decimals (fils).
export function money(amount: number | string | null | undefined, currency: string = MARKETPLACE_CURRENCY): string {
  if (amount === null || amount === undefined || amount === "") return "—";
  const value = Number(amount);
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency, currencyDisplay: "code" }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString()}`;
  }
}

// Stage 9.13: an amount typed on an Arabic keyboard arrives in Arabic-Indic
// digits (٠-٩, or the Persian ۰-۹) with "٫" as the decimal mark. Read those
// as the number they are instead of discarding them; grouping marks (",",
// "٬", "،") and anything else that isn't part of a number are dropped.
export function normalizeAmountInput(value: string): string {
  return value
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06f0))
    .replace(/٫/g, ".")
    .replace(/[^0-9.]/g, "");
}
