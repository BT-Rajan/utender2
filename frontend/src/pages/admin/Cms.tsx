import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import { ErrorBanner } from "@/components/ErrorBanner";
import { QueryError } from "@/components/QueryError";

interface CmsEntry {
  key: string;
  en: string;
  ar: string;
}

const KEY_LABELS: Record<string, string> = {
  support_contact: "How customers contact support (email / phone) -- shown on verification, suspension and billing problems",
  hero_heading: "Homepage headline",
  hero_subheading: "Homepage subheading",
  how_it_works_title: "\"How it works\" title",
  how_it_works_body: "\"How it works\" body",
  home_roles_heading: "Roles section · heading",
  home_roles_intro: "Roles section · introduction",
  home_owner_title: "Owner card · title",
  home_owner_who: "Owner card · who it's for",
  home_owner_step_1: "Owner card · step 1",
  home_owner_step_2: "Owner card · step 2",
  home_owner_step_3: "Owner card · step 3",
  home_owner_step_4: "Owner card · step 4",
  home_owner_after: "Owner card · after signup (the live owner document checklist is listed under it)",
  home_owner_cost: "Owner card · cost",
  home_owner_cta: "Owner card · signup button",
  home_provider_title: "Service provider card · title",
  home_provider_who: "Service provider card · who it's for",
  home_provider_step_1: "Service provider card · step 1",
  home_provider_step_2: "Service provider card · step 2",
  home_provider_step_3: "Service provider card · step 3",
  home_provider_step_4: "Service provider card · step 4",
  home_provider_after: "Service provider card · after signup (the live service provider document checklist is listed under it)",
  home_provider_cost: "Service provider card · cost (live subscription prices from Stripe are listed under it — don't type prices here)",
  home_provider_cta: "Service provider card · signup button",
  signup_owner_hint: "Signup form · Owner explanation",
  signup_provider_hint: "Signup form · Service provider explanation (live prices are added under it)",
};

function CmsRow({ entry }: { entry: CmsEntry }) {
  const queryClient = useQueryClient();
  const [en, setEn] = useState(entry.en);
  const [ar, setAr] = useState(entry.ar);
  const [error, setError] = useState<string | null>(null);

  // Local edit buffers only start from the fetched value — after a save or
  // reset, the query refetches and this entry's props change (same key, so
  // React reuses the component instance), so re-sync here rather than only
  // on first mount.
  useEffect(() => {
    setEn(entry.en);
    setAr(entry.ar);
  }, [entry.en, entry.ar]);

  const invalidate = () => {
    setError(null);
    queryClient.invalidateQueries({ queryKey: ["admin-cms"] });
  };

  const saveMutation = useMutation({
    mutationFn: (language: "en" | "ar") =>
      apiFetch(`/admin/cms/${entry.key}/${language}`, { method: "PUT", body: { value: language === "en" ? en : ar } }),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not save."),
  });

  const resetMutation = useMutation({
    mutationFn: (language: "en" | "ar") => apiFetch(`/admin/cms/${entry.key}/${language}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (err) => setError(err instanceof ApiError ? err.detail : "Could not reset."),
  });

  return (
    <div className="bg-white border border-border rounded px-5 py-4.5">
      <h3 className="font-display font-semibold text-sm text-navy mb-3">{KEY_LABELS[entry.key] ?? entry.key}</h3>
      <ErrorBanner message={error} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block font-mono text-[10px] uppercase tracking-wide text-steel mb-1">English</label>
          <textarea value={en} onChange={(e) => setEn(e.target.value)} rows={3} className="w-full border border-border rounded px-3 py-2 text-sm resize-y" />
          <div className="flex gap-2 mt-1.5">
            <button
              type="button"
              onClick={() => saveMutation.mutate("en")}
              disabled={saveMutation.isPending}
              className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-3 py-1.5"
            >
              Save
            </button>
            <button type="button" onClick={() => resetMutation.mutate("en")} className="text-xs text-steel-light underline">
              Reset to default
            </button>
          </div>
        </div>
        <div dir="rtl">
          <label className="block font-mono text-[10px] uppercase tracking-wide text-steel mb-1 text-right">العربية</label>
          <textarea value={ar} onChange={(e) => setAr(e.target.value)} rows={3} className="w-full border border-border rounded px-3 py-2 text-sm resize-y text-right" />
          <div className="flex gap-2 mt-1.5 justify-end">
            <button
              type="button"
              onClick={() => saveMutation.mutate("ar")}
              disabled={saveMutation.isPending}
              className="border border-navy text-navy hover:bg-navy hover:text-white text-xs font-semibold rounded px-3 py-1.5"
            >
              حفظ
            </button>
            <button type="button" onClick={() => resetMutation.mutate("ar")} className="text-xs text-steel-light underline">
              إعادة للافتراضي
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AdminCmsPage() {
  const {
    data: entries,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["admin-cms"],
    queryFn: () => apiFetch<CmsEntry[]>("/admin/cms"),
  });

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <div className="mb-6">
        <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">Admin · Public site</span>
        <h1 className="font-display text-2xl font-semibold text-navy mb-1">Website content</h1>
        <p className="text-[13.5px] text-steel">Edit the public homepage and signup copy in both English and Arabic. Live data is never typed here: statistics, the verification document checklists (managed under Document requirements) and subscription prices (the Stripe prices) are always shown from their real source.</p>
      </div>

      {isError ? (
        <QueryError onRetry={() => refetch()} />
      ) : (
        <div className="grid gap-4">{entries?.map((entry) => <CmsRow key={entry.key} entry={entry} />)}</div>
      )}
    </main>
  );
}
