import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "@/api/client";
import type { Project, ProjectDetail, TenderType } from "@/api/types";
import { useI18n } from "@/i18n/I18nContext";
import { localInputToUtcIso } from "@/lib/dates";
import { KUWAIT_GOVERNORATES } from "@/lib/location";
import { CategoryField } from "@/components/CategoryField";
import { formatDeadline } from "@/lib/format";

export function OwnerProjectNewPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const formRef = useRef<HTMLFormElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const creationToken = useRef(
    typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
  );
  const [tenderType, setTenderType] = useState<TenderType>("owner_visible");

  const defaultDeadline = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  const defaultDeadlineValue = new Date(defaultDeadline.getTime() - defaultDeadline.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);

  // Stage 3.11: offer the drafts already in progress before starting another.
  const { data: myProjects } = useQuery({
    queryKey: ["owner-projects"],
    queryFn: () => apiFetch<Project[]>("/owner/projects"),
  });
  const drafts = (myProjects ?? []).filter((p) => p.status === "draft");

  async function submitProject(status: "draft" | "open") {
    setError(null);
    const formEl = formRef.current;
    if (!formEl) return;
    if (!formEl.reportValidity()) return;

    const form = new FormData(formEl);
    if (!form.get("title") || !form.get("address") || !form.get("bid_deadline")) {
      setError(t("owner.projectNew.validationError"));
      return;
    }
    // datetime-local is the owner's local time; send the instant explicitly.
    form.set("bid_deadline", localInputToUtcIso(form.get("bid_deadline") as string));
    form.set("tender_type", tenderType);
    form.set("status", status);
    // Stage 3.11: one draft per start, however many times this is sent.
    form.set("creation_token", creationToken.current);

    setPending(true);
    try {
      const project = await apiFetch<ProjectDetail>("/projects", { method: "POST", formData: form });
      navigate(`/owner/projects/${project.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : t("owner.projectNew.submitError"));
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="max-w-4xl mx-auto px-5 py-8">
      <span className="font-mono text-[10.5px] uppercase tracking-widest text-amber-dark block mb-1">{t("owner.projectNew.eyebrow")}</span>
      <h1 className="font-display text-2xl font-semibold text-navy mb-1">{t("owner.projectNew.heading")}</h1>
      <p className="text-[13.5px] text-steel mb-6">{t("owner.projectNew.description")}</p>

      {drafts.length > 0 && (
        <div className="border border-border bg-blue-tint/40 rounded px-4 py-3 mb-5 max-w-2xl text-sm">
          <strong className="font-display text-navy block">{t("draftDetails.resumeHeading")}</strong>
          <p className="text-steel text-[13px] mb-1">{t("draftDetails.resumeHint")}</p>
          <ul className="list-disc ps-5">
            {drafts.slice(0, 5).map((d) => (
              <li key={d.id}>
                <Link to={`/owner/projects/${d.id}`} className="text-blue underline">
                  {d.title || t("draftDetails.untitled")}
                </Link>
                {d.updated_at && <span className="text-steel-light text-xs"> · {formatDeadline(d.updated_at)}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p className="text-xs bg-red-tint text-red border border-red rounded px-3 py-2.5 mb-5 max-w-2xl">{error}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-6 items-start">
        <form
          ref={formRef}
          onSubmit={(e) => {
            // The form's implicit submit (e.g. Enter in a field) only ever
            // saves a draft; publishing needs the explicit "Post" button.
            e.preventDefault();
            submitProject("draft");
          }}
          className="grid gap-[18px]"
        >
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("owner.projectNew.tenderType")}</label>
            <div className="flex border border-navy rounded overflow-hidden w-fit">
              <button
                type="button"
                onClick={() => setTenderType("owner_visible")}
                className={`px-4 py-2 text-xs font-mono uppercase ${tenderType === "owner_visible" ? "bg-navy text-white" : "bg-white text-navy"}`}
              >
                {t("owner.projectNew.ownerVisibleToggle")}
              </button>
              <button
                type="button"
                onClick={() => setTenderType("sealed")}
                className={`px-4 py-2 text-xs font-mono uppercase border-s border-navy ${tenderType === "sealed" ? "bg-navy text-white" : "bg-white text-navy"}`}
              >
                {t("owner.projectNew.sealedToggle")}
              </button>
            </div>
            <p className="text-xs text-steel-light mt-1.5">
              {tenderType === "sealed" ? t("owner.projectNew.sealedHint") : t("owner.projectNew.ownerVisibleHint")}
            </p>
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("owner.projectNew.title")}</label>
            <input
              name="title"
              required
              placeholder={t("owner.projectNew.titlePlaceholder")}
              className="w-full border border-border rounded px-3 py-2.5 text-sm"
            />
          </div>
          <div>
            <div className="grid sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label htmlFor="new-governorate" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("location.governorate")}</label>
                <select id="new-governorate" name="governorate" defaultValue="" className="w-full border border-border rounded px-3 py-2.5 text-sm">
                  <option value="">{t("location.chooseGovernorate")}</option>
                  {KUWAIT_GOVERNORATES.map((g) => (
                    <option key={g} value={g}>
                      {t(`location.${g}`)}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="new-area" className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("location.area")}</label>
                <input id="new-area" name="area" maxLength={100} className="w-full border border-border rounded px-3 py-2.5 text-sm" />
              </div>
            </div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("location.address")}</label>
            <input name="address" required placeholder={t("owner.projectNew.addressPlaceholder")} className="w-full border border-border rounded px-3 py-2.5 text-sm" />
            <p className="text-xs text-steel-light mt-1.5">{t("location.addressHint")}</p>
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("owner.projectNew.trade")}</label>
            <CategoryField name="trade" placeholder={t("owner.projectNew.tradePlaceholder")} className="w-full border border-border rounded px-3 py-2.5 text-sm" />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("owner.projectNew.scope")}</label>
            <textarea
              name="description"
              rows={4}
              placeholder={t("owner.projectNew.scopePlaceholder")}
              className="w-full border border-border rounded px-3 py-2.5 text-sm resize-y"
            />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("owner.projectNew.drawings")}</label>
            <div className="border border-dashed border-blue bg-blue-tint rounded px-4 py-6 text-center">
              <input type="file" name="drawings" multiple accept=".pdf,.dwg,.xlsx,.docx,.jpg,.jpeg,.png,.zip" className="text-xs mx-auto" />
              <p className="text-[11px] text-blue mt-2">{t("owner.projectNew.drawingsHint")}</p>
            </div>
            <p className="text-xs text-steel-light mt-1.5">{t("owner.projectNew.drawingsAccessNote")}</p>
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wide text-steel mb-1.5">{t("owner.projectNew.deadline")}</label>
            <input
              type="datetime-local"
              name="bid_deadline"
              required
              defaultValue={defaultDeadlineValue}
              className="border border-border rounded px-3 py-2.5 text-sm"
            />
            <p className="text-xs text-steel-light mt-1.5">{t("owner.projectNew.deadlineNote")}</p>
          </div>
          <div className="flex items-center gap-3 mt-1">
            <button
              type="button"
              disabled={pending}
              onClick={() => submitProject("open")}
              className="bg-amber hover:bg-amber-dark disabled:opacity-60 text-white font-semibold text-sm rounded px-5 py-2.5 w-fit"
            >
              {pending ? t("owner.projectNew.posting") : t("owner.projectNew.postProject")}
            </button>
            <button
              type="submit"
              disabled={pending}
              className="border border-navy text-navy hover:bg-navy hover:text-white disabled:opacity-60 text-sm font-semibold rounded px-5 py-2.5 w-fit"
            >
              {t("owner.projectNew.saveAsDraft")}
            </button>
          </div>
          <p className="text-xs text-steel-light -mt-2.5">{t("owner.projectNew.draftNote")}</p>
        </form>

        <div className="bg-white border border-border rounded px-4.5 py-4">
          <h3 className="font-mono text-[13px] uppercase tracking-wide text-navy mb-2">{t("owner.projectNew.sidebarHeading")}</h3>
          <ul className="text-[13px] text-steel leading-[1.7] list-disc pl-[18px]">
            <li>{t("owner.projectNew.tip1")}</li>
            <li>{t("owner.projectNew.tip2")}</li>
            <li>{t("owner.projectNew.tip3")}</li>
          </ul>
        </div>
      </div>
    </main>
  );
}
