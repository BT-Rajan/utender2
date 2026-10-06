import { NavLink, Outlet } from "react-router-dom";
import { AppHeader } from "@/components/AppHeader";
import { useI18n } from "@/i18n/I18nContext";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `font-mono text-xs uppercase tracking-wide ${isActive ? "text-navy" : "text-steel hover:text-navy"}`;

export function AdminLayout() {
  const { t } = useI18n();
  return (
    <div className="min-h-screen">
      <AppHeader roleLabel="Site Admin" homeHref="/admin/requirements" />
      <div className="max-w-5xl mx-auto px-5 pt-4 flex flex-wrap gap-x-4 gap-y-2">
        <NavLink to="/admin/requirements" className={navClass}>
          {t("admin.nav.requirements")}
        </NavLink>
        <NavLink to="/admin/review" className={navClass}>
          {t("admin.nav.review")}
        </NavLink>
        <NavLink to="/admin/service-providers" className={navClass}>
          {t("admin.nav.service_providers")}
        </NavLink>
        <NavLink to="/admin/owners" className={navClass}>
          {t("admin.nav.owners")}
        </NavLink>
        <NavLink to="/admin/projects" className={navClass}>
          {t("admin.nav.projects")}
        </NavLink>
        <NavLink to="/admin/offers" className={navClass}>
          {t("admin.nav.offers")}
        </NavLink>
        <NavLink to="/admin/cms" className={navClass}>
          {t("admin.nav.cms")}
        </NavLink>
      </div>
      <Outlet />
    </div>
  );
}
