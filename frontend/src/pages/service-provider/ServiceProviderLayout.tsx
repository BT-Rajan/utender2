import { Outlet } from "react-router-dom";
import { AppHeader } from "@/components/AppHeader";
import { useI18n } from "@/i18n/I18nContext";

export function ServiceProviderLayout() {
  const { t } = useI18n();
  return (
    <div className="min-h-screen">
      <AppHeader roleLabel={t("service_provider.roleLabel")} homeHref="/service-provider/dashboard" />
      <Outlet />
    </div>
  );
}
