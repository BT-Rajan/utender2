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
