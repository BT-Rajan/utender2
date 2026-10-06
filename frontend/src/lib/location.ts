// Stage 3.5: Kuwait's governorates (keys match backend/app/services/locations.py;
// display names are in the "location" dictionary namespace).
export const KUWAIT_GOVERNORATES = ["capital", "hawalli", "farwaniya", "mubarak_al_kabeer", "ahmadi", "jahra"] as const;

// "Mishref, Mubarak Al-Kabeer" -- the listing-level location.
export function formatArea(t: (key: string) => string, governorate: string | null, area: string | null): string {
  const parts = [area, governorate ? t(`location.${governorate}`) : null].filter(Boolean);
  return parts.length ? parts.join(", ") : t("location.notSpecified");
}
