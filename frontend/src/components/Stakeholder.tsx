import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import { ErrorBanner } from "@/components/ErrorBanner";
import { useI18n } from "@/i18n/I18nContext";

// Step 3: who a registered account represents. The person logged in is
// always themselves; the stakeholder is either that person or an
// organization they are authorized to act for. Served by /account/identity.

export type StakeholderType = "individual" | "organization";

export interface Stakeholder {
  id: string;
  side: "owner" | "service_provider";
  type: StakeholderType | null;
  display_name: string | null;
  organization: {
    id: string;
    legal_name: string;
    member_count: number;
    membership: { role: "admin" | "member"; position: string | null } | null;
    authorized_representative: { user_id: string; full_name: string | null; email: string; position: string | null } | null;
  } | null;
  status: {
    account_created: boolean;
    stakeholder_established: boolean;
    verified: boolean;
    eligible: boolean;
    verification_status: string;
    marketplace_status: string;
  };
  editable: boolean;
}

export interface Identity {
  person: { user_id: string; full_name: string | null; email: string };
  role: string;
  stakeholder: Stakeholder | null;
  acting_as: { kind: StakeholderType; stakeholder_id: string; name: string | null } | null;
}

export function useIdentity() {
  return useQuery({ queryKey: ["identity"], queryFn: () => apiFetch<Identity>("/account/identity") });
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-wide text-steel mb-1">{children}</div>;
}

// Account created -> identity established -> verified -> eligible.
export function StakeholderProgress({ status }: { status: Stakeholder["status"] }) {
  const { t } = useI18n();
  const steps: [string, boolean][] = [
    [t("stakeholder.accountCreated"), status.account_created],
    [t("stakeholder.established"), status.stakeholder_established],
    [t("stakeholder.verified"), status.verified],
    [t("stakeholder.eligible"), status.eligible],
  ];
  return (
    <ol className="flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
      {steps.map(([label, done]) => (
        <li key={label} className={done ? "text-green" : "text-steel-light"}>
          <span className="font-mono">{done ? "✓" : "○"}</span> {label}
        </li>
      ))}
    </ol>
  );
}

export function StakeholderSummary({ stakeholder, viewerIsAdmin = false }: { stakeholder: Stakeholder; viewerIsAdmin?: boolean }) {
  const { t } = useI18n();
  const org = stakeholder.organization;
  if (!stakeholder.type) return <p className="text-sm text-steel">{t("stakeholder.notEstablished")}</p>;
  const rep = org?.authorized_representative;
  return (
    <div className="grid gap-3 text-sm">
      <div>
        <Label>{t("stakeholder.actingAs")}</Label>
        <div className="text-navy font-semibold">
          {stakeholder.type === "organization" ? org?.legal_name : stakeholder.display_name}{" "}
          <span className="font-mono text-[10px] uppercase text-steel font-normal">
            · {stakeholder.type === "organization" ? t("stakeholder.typeOrganization") : t("stakeholder.typeIndividual")}
          </span>
        </div>
      </div>
      {org && !viewerIsAdmin && org.membership && (
        <div>
          <Label>{t("stakeholder.yourRole")}</Label>
          <div className="text-navy">
            {org.membership.role === "admin" ? t("stakeholder.representative") : t("stakeholder.member")}
            {org.membership.position && <span className="text-steel"> · {org.membership.position}</span>}
          </div>
        </div>
      )}
      {org && viewerIsAdmin && rep && (
        <div>
          <Label>{t("stakeholder.representative")}</Label>
          <div className="text-navy">
            {rep.full_name} <span className="text-steel">· {rep.email}</span>
            {rep.position && <span className="text-steel"> · {rep.position}</span>}
          </div>
        </div>
      )}
      <StakeholderProgress status={stakeholder.status} />
    </div>
  );
}

// Shown at the top of the verification page: establish (or correct, before
// review) who this account represents.
export function StakeholderSection() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const { data: identity } = useIdentity();
  const stakeholder = identity?.stakeholder;
  const [editing, setEditing] = useState(false);
  const [type, setType] = useState<StakeholderType | null>(null);
  const [legalName, setLegalName] = useState("");
  const [position, setPosition] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!stakeholder) return;
    setType(stakeholder.type);
    setLegalName(stakeholder.organization?.legal_name ?? "");
    setPosition(stakeholder.organization?.membership?.position ?? "");
    setAuthorized(stakeholder.type === "organization");
  }, [stakeholder]);

  const save = useMutation({
    mutationFn: () =>
      apiFetch<Identity>("/account/stakeholder", {
        method: "PUT",
        body: type === "organization" ? { type, legal_name: legalName, position: position || null, authorized } : { type },
      }),
    onSuccess: (data) => {
      setError(null);
      setEditing(false);
      queryClient.setQueryData(["identity"], data);
      // The verification checklist depends on the stakeholder type, and display
      // names (e.g. a service provider's trading name) may have changed.
      for (const key of ["owner-documents", "service-provider-documents", "owner-profile", "service-provider-profile"]) {
        queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
    onError: (err) => setError(err instanceof ApiError ? err.detail : t("stakeholder.saveError")),
  });

  if (!stakeholder) return null;
  const side = stakeholder.side;
  const showForm = stakeholder.editable && (editing || !stakeholder.type);

  return (
    <section className="bg-white border border-border border-t-4 border-t-navy rounded px-6 py-5 mb-8 max-w-xl">
      <h2 className="font-display text-lg font-semibold text-navy mb-1">{t("stakeholder.heading")}</h2>
      <p className="text-[13px] text-steel mb-4">{t("stakeholder.intro")}</p>
      <ErrorBanner message={error} />

      {!showForm ? (
        <div className="flex items-start justify-between gap-4">
          <StakeholderSummary stakeholder={stakeholder} />
          {stakeholder.editable ? (
            <button type="button" onClick={() => setEditing(true)} className="text-xs text-steel underline shrink-0">
              {t("stakeholder.change")}
            </button>
          ) : null}
        </div>
      ) : (
        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          {(["individual", "organization"] as const).map((option) => (
            <label
              key={option}
              className={`flex gap-3 items-start border rounded px-3 py-2.5 cursor-pointer ${type === option ? "border-navy bg-blue-tint" : "border-border"}`}
            >
              <input type="radio" name="stakeholder_type" checked={type === option} onChange={() => setType(option)} className="mt-1" />
              <span>
                <span className="block font-semibold text-navy text-sm">{t(`stakeholder.${option}_${side}`)}</span>
                <span className="block text-xs text-steel">{t(`stakeholder.${option}_${side}_hint`)}</span>
              </span>
            </label>
          ))}

          {type === "organization" && (
            <div className="grid gap-3 ps-1">
              <div>
                <Label>{t("stakeholder.legalName")}</Label>
                <input value={legalName} onChange={(e) => setLegalName(e.target.value)} required className="w-full border border-border rounded px-3 py-2 text-sm" />
              </div>
              <div>
                <Label>{t("stakeholder.position")}</Label>
                <input
                  value={position}
                  onChange={(e) => setPosition(e.target.value)}
                  placeholder={t("stakeholder.positionPlaceholder")}
                  className="w-full border border-border rounded px-3 py-2 text-sm"
                />
              </div>
              <label className="flex gap-2 items-start text-[13px] text-navy">
                <input type="checkbox" checked={authorized} onChange={(e) => setAuthorized(e.target.checked)} required className="mt-0.5" />
                {t("stakeholder.authorized")}
              </label>
            </div>
          )}

          <div className="flex gap-3 items-center">
            <button
              type="submit"
              disabled={!type || save.isPending}
              className="bg-navy hover:bg-navy-deep disabled:opacity-60 text-white text-sm font-semibold rounded px-4 py-2"
            >
              {save.isPending ? t("stakeholder.saving") : t("stakeholder.save")}
            </button>
            {stakeholder.type && (
              <button type="button" onClick={() => setEditing(false)} className="text-xs text-steel underline">
                {t("common.cancel")}
              </button>
            )}
          </div>
        </form>
      )}
      {!stakeholder.editable && stakeholder.type && <p className="text-xs text-steel-light mt-3">{t("stakeholder.locked")}</p>}
    </section>
  );
}
