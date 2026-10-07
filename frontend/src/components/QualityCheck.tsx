import { useI18n } from "@/i18n/I18nContext";

export interface QualityIssue {
  code: string;
  section: string;
  message: string;
  params: Record<string, string | number>;
}
export interface QualityReport {
  ready: boolean;
  errors: QualityIssue[];
  warnings: QualityIssue[];
}

// Stage 3.12: what is still missing before this requirement goes in front of
// providers. The report (GET /projects/{id}/quality) is the same check that
// refuses publication; the page re-reads it after every save.
function issueText(t: (k: string) => string, issue: QualityIssue): string {
  const key = `quality.${issue.code}`;
  const text = t(key);
  if (text === key) return issue.message; // no translation: the server's own wording
  return Object.entries(issue.params).reduce((s, [k, v]) => s.replace(`{${k}}`, String(v)), text);
}

function IssueList({ issues, tone }: { issues: QualityIssue[]; tone: "error" | "warning" }) {
  const { t } = useI18n();
  return (
    <ul className="grid gap-1.5">
      {issues.map((issue, i) => (
        <li key={issue.code + i} className="flex items-start gap-2 text-sm">
          <span className={tone === "error" ? "text-red" : "text-amber-dark"}>{tone === "error" ? "✕" : "!"}</span>
          <span className="flex-1 text-navy">
            {issueText(t, issue)}{" "}
            <a href={`#section-${issue.section}`} className="text-blue underline text-xs whitespace-nowrap">
              {t(`quality.section_${issue.section}`)}
            </a>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function QualityCheck({ report }: { report: QualityReport | undefined }) {
  const { t } = useI18n();
  if (!report) return null;
  return (
    <section id="quality-check" className={`border rounded px-5 py-4 mb-6 max-w-2xl ${report.ready ? "border-green bg-green-tint/40" : "border-red/40 bg-red-tint/30"}`}>
      <h2 className="font-display text-base font-semibold text-navy mb-1">
        {report.ready ? `✓ ${t("quality.ready")}` : t("quality.notReady").replace("{count}", String(report.errors.length))}
      </h2>
      <p className="text-xs text-steel mb-3">{report.ready ? t("quality.readyHint") : t("quality.notReadyHint")}</p>
      {report.errors.length > 0 && <IssueList issues={report.errors} tone="error" />}
      {report.warnings.length > 0 && (
        <div className={report.errors.length ? "mt-3 pt-3 border-t border-border" : ""}>
          <div className="font-mono text-[10.5px] uppercase tracking-wide text-steel mb-1.5">{t("quality.warningsHeading")}</div>
          <IssueList issues={report.warnings} tone="warning" />
        </div>
      )}
    </section>
  );
}
