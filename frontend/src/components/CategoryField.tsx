import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import type { ServiceCategory } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";

export function useCategories() {
  return useQuery({ queryKey: ["categories"], queryFn: () => apiFetch<ServiceCategory[]>("/categories"), staleTime: 60_000 });
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
