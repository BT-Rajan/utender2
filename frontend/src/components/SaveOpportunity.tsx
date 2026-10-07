import { type InfiniteData, useMutation, useQueryClient } from "@tanstack/react-query";
import type { FeedPage, Project, ProjectDetail } from "@/api/types";
import { apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";

// Stage 4.8: save / unsave an opportunity. Both are idempotent on the server,
// so a double click or a stale page never makes a duplicate or an error;
// every view showing the saved state is refreshed from the server after.
type FeedPages = InfiniteData<FeedPage>;

export function useSaveToggle() {
  const queryClient = useQueryClient();
  // The new state shows at once on every view (so a second click acts on
  // what the provider sees, not on a page that hasn't caught up), and is
  // put back if the server refuses.
  const mark = (projectId: string, saved: boolean) => {
    queryClient.setQueriesData<FeedPages>({ queryKey: ["service-provider-feed"] }, (data) =>
      data && { ...data, pages: data.pages.map((page) => ({ ...page, items: page.items.map((p) => (p.id === projectId ? { ...p, saved } : p)) })) },
    );
    queryClient.setQueryData<Project[]>(["saved-opportunities"], (rows) => rows && (saved ? rows : rows.filter((p) => p.id !== projectId)));
    queryClient.setQueryData<ProjectDetail>(["project", projectId], (p) => p && { ...p, saved });
  };
  return useMutation({
    mutationFn: ({ projectId, save }: { projectId: string; save: boolean }) =>
      apiFetch(`/service-provider/saved/${projectId}`, { method: save ? "PUT" : "DELETE" }),
    onMutate: async ({ projectId, save }) => {
      await queryClient.cancelQueries({ queryKey: ["service-provider-feed"] });
      mark(projectId, save);
    },
    onError: (_err, { projectId, save }) => mark(projectId, !save),
    onSettled: (_data, _err, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: ["service-provider-feed"] });
      queryClient.invalidateQueries({ queryKey: ["saved-opportunities"] });
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export function SaveButton({ projectId, saved }: { projectId: string; saved: boolean }) {
  const { t } = useI18n();
  const toggle = useSaveToggle();
  return (
    <button
      type="button"
      disabled={toggle.isPending}
      onClick={() => toggle.mutate({ projectId, save: !saved })}
      aria-pressed={saved}
      className={`text-xs font-semibold rounded px-3 py-1.5 border ${saved ? "bg-amber text-white border-amber" : "border-navy text-navy bg-white"}`}
      data-testid="save-toggle"
    >
      {saved ? `★ ${t("saved.saved")} · ${t("saved.unsave")}` : `☆ ${t("saved.saveForLater")}`}
    </button>
  );
}
