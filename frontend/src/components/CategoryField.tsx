import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ServiceCategory } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";

export function useCategories() {
  return useQuery({ queryKey: ["categories"], queryFn: () => apiFetch<ServiceCategory[]>("/categories"), staleTime: 60_000 });
}

// What a provider does, as admins read it: the types of work it chose on its
// profile, else the older free-text trade.
export function useWorkLabel(): (p: { service_categories?: string[]; primary_trade?: string | null }) => string {
  const { data } = useCategories();
  return (p) => {
    const names = (p.service_categories ?? []).map((id) => data?.find((c) => c.id === id)?.name).filter(Boolean);
    return names.length ? names.join(", ") : p.primary_trade || "Types of work not chosen yet";
  };
}

// The type of work: one of the platform's service categories (admin-managed),
// or free text while the platform has none. A chosen name links the category
// server-side (services.categories.resolve_trade).
export function CategoryField({
  id,
  name,
  value,
  onChange,
  placeholder,
  className,
}: {
  id?: string;
  name?: string;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  className: string;
}) {
  const { t } = useI18n();
  const { data: categories = [] } = useCategories();
  if (categories.length === 0) {
    return (
      <input
        id={id}
        name={name}
        value={value}
        onChange={onChange && ((e) => onChange(e.target.value))}
        placeholder={placeholder}
        maxLength={100}
        className={className}
      />
    );
  }
  const legacy = value && !categories.some((c) => c.name === value) ? value : null;
  return (
    <select id={id} name={name} value={value} onChange={onChange && ((e) => onChange(e.target.value))} className={className} defaultValue={value === undefined ? "" : undefined}>
      <option value="">{t("categoryPicker.choose")}</option>
      {legacy && <option value={legacy}>{legacy}</option>}
      {categories.map((c) => (
        <option key={c.id} value={c.name}>
          {c.name}
        </option>
      ))}
    </select>
  );
}
