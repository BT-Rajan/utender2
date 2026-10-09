import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";
import { fullDate } from "@/lib/format";

interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export function NotificationBell() {
  const { t, language } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: unread } = useQuery({
    queryKey: ["notifications-unread-count"],
    queryFn: () => apiFetch<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 60_000,
  });

  const { data: notifications } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => apiFetch<NotificationItem[]>("/notifications"),
    enabled: open,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
    queryClient.invalidateQueries({ queryKey: ["notifications-unread-count"] });
  };

  const markReadMutation = useMutation({
    mutationFn: (id: string) => apiFetch(`/notifications/${id}/read`, { method: "POST" }),
    onSuccess: invalidate,
  });

  const markAllReadMutation = useMutation({
    mutationFn: () => apiFetch("/notifications/read-all", { method: "POST" }),
    onSuccess: invalidate,
  });

  function handleClick(n: NotificationItem) {
    if (!n.is_read) markReadMutation.mutate(n.id);
    setOpen(false);
    if (n.link) navigate(n.link);
  }

  const count = unread?.count ?? 0;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative text-steel hover:text-navy"
        aria-label={t("common.notifications")}
      >
        <span className="text-base">🔔</span>
        {count > 0 && (
          <span className="absolute -top-1.5 -end-1.5 bg-red text-white text-[9px] font-mono font-bold rounded-full min-w-[16px] h-4 flex items-center justify-center px-1">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute end-0 mt-2 w-80 max-w-[calc(100vw-2.5rem)] max-h-96 overflow-y-auto bg-white border border-border rounded shadow-lg z-20">
            <div className="flex items-center justify-between px-3.5 py-2.5 border-b border-border">
              <span className="font-mono text-[10px] uppercase tracking-wide text-steel">{t("common.notifications")}</span>
              {count > 0 && (
                <button type="button" onClick={() => markAllReadMutation.mutate()} className="text-[11px] text-navy underline">
                  {t("common.markAllRead")}
                </button>
              )}
            </div>
            {!notifications?.length ? (
              <p className="px-3.5 py-6 text-center text-xs text-steel-light">{t("common.noNotifications")}</p>
            ) : (
              <ul>
                {notifications.map((n) => (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => handleClick(n)}
                      className={`w-full text-left px-3.5 py-2.5 border-b border-border last:border-0 hover:bg-blue-tint ${
                        n.is_read ? "opacity-60" : ""
                      }`}
                    >
                      <div className="font-display font-semibold text-[12.5px] text-navy">{n.title}</div>
                      <div className="text-[11.5px] text-steel mt-0.5">{n.body}</div>
                      <div className="font-mono text-[9.5px] text-steel-light mt-1">
                        {fullDate(n.created_at, language)}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
