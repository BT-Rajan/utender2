import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ApiError, apiFetch } from "@/api/client";
import { useI18n } from "@/i18n/I18nContext";

interface Found {
  user: { id: string; email: string; full_name: string | null; role: string; email_verified: boolean; deactivated_at: string | null; phone: string | null; language: string };
  acts_for: { stakeholder_id: string; display_name: string | null; organization: { legal_name: string } | null; standing: Record<string, unknown> | null } | null;
  membership: { role: string; position: string | null } | null;
}

async function lookup(email: string): Promise<Found | null> {
  try {
    return await apiFetch<Found>(`/admin/users?email=${encodeURIComponent(email)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

// Correcting a person's details -- the way back in for someone who has lost
// the mailbox their account was opened with. Only changed fields are sent; a
// changed email becomes unverified and gets a verification link.
function EditPerson({ user }: { user: Found["user"] }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<{ pending: boolean; error: string | null; saved: boolean }>({ pending: false, error: null, saved: false });

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body: Record<string, string> = {};
    for (const [field, current] of [["full_name", user.full_name ?? ""], ["email", user.email], ["phone", user.phone ?? ""], ["language", user.language]] as const) {
      const value = String(form.get(field) ?? "").trim();
      if (value !== current) body[field] = value;
    }
    const reason = String(form.get("reason") ?? "").trim();
    if (reason) body.reason = reason;
    setState({ pending: true, error: null, saved: false });
    try {
      await apiFetch(`/admin/users/${user.id}`, { method: "PATCH", body });
      setState({ pending: false, error: null, saved: true });
      await queryClient.invalidateQueries({ queryKey: ["admin-find"] });
    } catch (err) {
      setState({ pending: false, error: err instanceof ApiError ? err.message : t("support.failed"), saved: false });
    }
  }

  if (!open) {
    return <button type="button" onClick={() => setOpen(true)} className="mt-3 border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5">{t("support.editHeading")}</button>;
  }
  const input = "border border-border rounded px-3 py-1.5 text-sm w-full";
  const label = "block font-mono text-[10.5px] uppercase tracking-wide text-steel mb-1";
  return (
    <form key={`${user.id}:${user.email}:${user.full_name}:${user.phone}:${user.language}`} onSubmit={save} className="mt-3 grid gap-2.5 max-w-md" data-testid="edit-person">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy">{t("support.editHeading")}</h3>
      <div><label className={label} htmlFor="ep-name">{t("support.editName")}</label><input id="ep-name" name="full_name" defaultValue={user.full_name ?? ""} required className={input} dir="auto" /></div>
      <div><label className={label} htmlFor="ep-email">{t("support.editEmail")}</label><input id="ep-email" name="email" type="email" defaultValue={user.email} required className={input} dir="ltr" /><p className="text-[11.5px] text-steel mt-1">{t("support.editEmailNote")}</p></div>
      <div><label className={label} htmlFor="ep-phone">{t("support.editPhone")}</label><input id="ep-phone" name="phone" defaultValue={user.phone ?? ""} className={input} dir="ltr" /></div>
      <div><label className={label} htmlFor="ep-lang">{t("support.editLanguage")}</label>
        <select id="ep-lang" name="language" defaultValue={user.language} className={input}><option value="en">English</option><option value="ar">العربية</option></select></div>
      <div><label className={label} htmlFor="ep-reason">{t("support.editReason")}</label><input id="ep-reason" name="reason" maxLength={500} className={input} /></div>
      {state.error && <p role="alert" className="text-red text-xs">{state.error}</p>}
      {state.saved && <p className="text-green text-xs">{t("support.editSaved")}</p>}
      <button type="submit" disabled={state.pending} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 w-fit disabled:opacity-60">{state.pending ? t("support.editSaving") : t("support.editSave")}</button>
    </form>
  );
}

// Stage 9.4: find a person by email -- who they are, what they act for, and
// the state of both -- to start a support question from facts.
export function FindPerson() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [query, setQuery] = useState<string | null>(null);
  const { data, error, isFetching } = useQuery({ queryKey: ["admin-find", query], queryFn: () => lookup(query!), enabled: !!query, retry: false });
  const page = data?.acts_for && (data.user.role === "service_provider" ? "/admin/service-providers/" : "/admin/owners/") + data.acts_for.stakeholder_id;
  return (
    <section className="bg-white border border-border rounded px-4 py-3 text-sm" data-testid="find-person">
      <h2 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("support.find")}</h2>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQuery(email.trim()); }}>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("support.email")} aria-label={t("support.email")} className="border border-border rounded px-3 py-1.5 text-sm flex-1" />
        <button type="submit" disabled={!email.trim() || isFetching} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t("support.search")}</button>
      </form>
      {error && <p className="text-red mt-2" role="alert">{(error as Error).message}</p>}
      {query && data === null && <p className="text-steel mt-2">{t("support.notFound")}</p>}
      {data && (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-steel">{t("support.person")}</dt>
          <dd dir="auto">{data.user.full_name ?? "—"} · {data.user.email} · {data.user.role}{data.user.deactivated_at ? ` · ${t("support.deactivated")}` : ""}{!data.user.email_verified ? ` · ${t("support.emailUnverified")}` : ""}</dd>
          <dt className="text-steel">{t("support.actsFor")}</dt>
          <dd dir="auto">
            {data.acts_for ? (page ? <Link to={page} className="text-blue underline">{data.acts_for.organization?.legal_name ?? data.acts_for.display_name ?? "—"}</Link> : null) : t("support.notEstablished")}
            {data.membership && ` · ${data.membership.role === "admin" ? t("members.representative") : t("members.member")}`}
          </dd>
          {data.acts_for?.standing && (
            <>
              <dt className="text-steel">{t("support.standing")}</dt>
              <dd className="font-mono text-xs">{Object.entries(data.acts_for.standing).map(([k, v]) => `${k}: ${String(v)}`).join(" · ")}</dd>
            </>
          )}
        </dl>
      )}
      {data && data.user.role !== "admin" && <EditPerson user={data.user} />}
    </section>
  );
}

interface Check {
  project: { status: string; suspended: boolean; bid_deadline: string; paused: boolean; material_revision: number };
  participation: { status: string; action?: string | null; availability?: string };
  ineligibility_reasons: { code: string; message: string }[];
  offer: { status: string; suspended: boolean; based_on_material_revision: number; won: boolean } | null;
}

// Stage 9.4: why a provider can or can't respond to this requirement -- the
// same checks the offer endpoints enforce -- and where its own offer stands.
export function ProviderCheck({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [result, setResult] = useState<Check | string | null>(null);
  const run = async () => {
    try {
      const found = await lookup(email.trim());
      if (!found?.acts_for || found.user.role !== "service_provider") return setResult(t("support.notAProvider"));
      setResult(await apiFetch<Check>(`/admin/projects/${projectId}/provider-check/${found.acts_for.stakeholder_id}`));
    } catch (e) {
      setResult(e instanceof ApiError ? e.message : t("support.failed"));
    }
  };
  return (
    <div className="bg-white border border-border rounded px-5 py-4.5 text-sm" data-testid="provider-check">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("support.checkProvider")}</h3>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void run(); }}>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("support.providerEmail")} aria-label={t("support.providerEmail")} className="border border-border rounded px-3 py-1.5 text-sm flex-1" />
        <button type="submit" disabled={!email.trim()} className="border border-navy text-navy text-xs font-semibold rounded px-3 py-1.5 disabled:opacity-60">{t("support.check")}</button>
      </form>
      {typeof result === "string" && <p className="text-steel mt-2">{result}</p>}
      {result && typeof result !== "string" && (
        <ul className="mt-2 grid gap-1">
          <li>{t("support.participation")}: <span className="font-mono">{result.participation.status}{result.participation.action ? ` (${result.participation.action})` : ""}{result.participation.availability && result.participation.availability !== "open" ? ` · ${result.participation.availability}` : ""}</span></li>
          {result.ineligibility_reasons.map((r) => <li key={r.code} className="text-amber-dark">{r.message}</li>)}
          <li>
            {t("support.offer")}:{" "}
            {result.offer
              ? <span className="font-mono">{result.offer.status}{result.offer.suspended ? " · suspended" : ""}{result.offer.won ? " · won" : ""} · v{result.offer.based_on_material_revision} / v{result.project.material_revision}</span>
              : t("support.noOffer")}
          </li>
        </ul>
      )}
    </div>
  );
}

// Stage 9.4: what blocks this requirement's publication -- the same check the
// owner's Publish button runs. Shown for drafts.
export function PublishCheck({ projectId }: { projectId: string }) {
  const { t } = useI18n();
  const { data } = useQuery({
    queryKey: ["admin-quality", projectId],
    queryFn: () => apiFetch<{ owner_can_publish: boolean; errors: { code: string; message: string }[]; warnings: { code: string; message: string }[] }>(`/admin/projects/${projectId}/quality`),
  });
  if (!data) return null;
  return (
    <div className="bg-white border border-border rounded px-5 py-4.5 text-sm" data-testid="publish-check">
      <h3 className="font-mono text-[11px] uppercase tracking-wide text-navy mb-2">{t("support.publishCheck")}</h3>
      {!data.owner_can_publish && <p className="text-red">{t("support.ownerCannotPublish")}</p>}
      {data.errors.length ? <ul className="list-disc ps-5 text-red">{data.errors.map((e) => <li key={e.code}>{e.message}</li>)}</ul> : <p className="text-green">{t("support.noBlockers")}</p>}
      {!!data.warnings.length && <ul className="list-disc ps-5 text-steel mt-1">{data.warnings.map((w) => <li key={w.code}>{w.message}</li>)}</ul>}
    </div>
  );
}
