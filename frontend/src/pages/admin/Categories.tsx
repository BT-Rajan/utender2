import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { ServiceCategory } from "@/api/types";
import { ErrorBanner } from "@/components/ErrorBanner";
import { QueryError } from "@/components/QueryError";

// Stage 3.9: the platform's list of service categories (types of work).
// Owners file requirements under one; providers declare the ones they offer;
// an owner may then limit a requirement to providers who offer its category.
// Categories are deactivated, never deleted, so nothing already filed changes.
export function AdminCategoriesPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: categories, isError, refetch } = useQuery({
    queryKey: ["admin-categories"],
    queryFn: () => apiFetch<ServiceCategory[]>("/admin/categories"),
  });
  const done = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-categories"] });
    queryClient.invalidateQueries({ queryKey: ["categories"] });
  };
  const fail = (err: unknown) => setError(err instanceof ApiError ? err.detail : "Could not save the category.");

  const add = useMutation({
    mutationFn: () => apiFetch("/admin/categories", { method: "POST", body: { name } }),
    onSuccess: () => {
      setName("");
      done();
    },
    onError: fail,
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name?: string; is_active?: boolean } }) =>
      apiFetch(`/admin/categories/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      setEditing(null);
      done();
    },
    onError: fail,
  });

  return (
    <main className="max-w-3xl mx-auto px-5 py-8">
      <h1 className="font-display text-2xl font-semibold text-navy mb-1">Service categories</h1>
      <p className="text-[13.5px] text-steel mb-5">
        Types of work owners file requirements under and providers say they offer. Renaming updates every requirement filed under the
        category; deactivating stops it being offered for new requirements and profiles.
      </p>
      <ErrorBanner message={error} />
      <form
        className="flex gap-2 mb-6"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Electrical works"
          aria-label="Category name"
          maxLength={100}
          required
          className="flex-1 border border-border rounded px-3 py-2 text-sm"
        />
        <button type="submit" disabled={add.isPending} className="bg-navy hover:bg-navy-deep disabled:opacity-50 text-white text-sm font-semibold rounded px-4 py-2">
          Add category
        </button>
      </form>
      {isError ? (
        <QueryError onRetry={() => refetch()} />
      ) : (
        <ul className="divide-y divide-border border border-border rounded bg-white">
          {categories?.length === 0 && <li className="px-4 py-3 text-sm text-steel-light">No categories yet.</li>}
          {categories?.map((c) => (
            <li key={c.id} className="px-4 py-2.5 flex items-center gap-3 flex-wrap">
              {editing?.id === c.id ? (
                <>
                  <input
                    value={editing.name}
                    onChange={(e) => setEditing({ id: c.id, name: e.target.value })}
                    aria-label="New name"
                    maxLength={100}
                    className="flex-1 border border-border rounded px-2 py-1 text-sm"
                  />
                  <button type="button" onClick={() => patch.mutate({ id: c.id, body: { name: editing.name } })} className="text-xs text-blue underline">
                    Save
                  </button>
                  <button type="button" onClick={() => setEditing(null)} className="text-xs text-steel underline">
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <span className={`flex-1 text-sm ${c.is_active ? "text-navy" : "text-steel-light line-through"}`}>{c.name}</span>
                  <button type="button" onClick={() => setEditing({ id: c.id, name: c.name })} className="text-xs text-blue underline">
                    Rename
                  </button>
                  <button type="button" onClick={() => patch.mutate({ id: c.id, body: { is_active: !c.is_active } })} className="text-xs text-steel underline">
                    {c.is_active ? "Deactivate" : "Reactivate"}
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
