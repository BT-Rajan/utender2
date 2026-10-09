import { useI18n } from "@/i18n/I18nContext";
import { usePublicCms } from "@/lib/publicInfo";

// Stage 9.13: how to reach the U-Tender team, wherever the app tells a
// customer to "contact support". Set by an admin (Content -> support_contact);
// shows nothing until then rather than an address nobody reads.
export function SupportContact() {
  const { t, language } = useI18n();
  const { data } = usePublicCms(language);
  const contact = data?.support_contact?.trim();
  if (!contact) return null;
  return (
    <p className="text-sm text-steel mt-2" dir="auto">
      {t("common.supportContact")} <span className="text-navy font-semibold">{contact}</span>
    </p>
  );
}
