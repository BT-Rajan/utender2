import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

// A draft requirement is edited in several sections, each with its own Save.
// Each section reports whether it has unsaved changes, so the page can say so
// before publishing (published rules can't be changed) and the browser asks
// before the tab is closed or reloaded -- nothing typed is lost silently.
interface Unsaved {
  report: (section: string, dirty: boolean) => void;
  sections: string[];
}

const UnsavedContext = createContext<Unsaved>({ report: () => {}, sections: [] });

export function UnsavedSectionsProvider({ children }: { children: ReactNode }) {
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const report = useCallback((section: string, isDirty: boolean) => {
    setDirty((current) => (!!current[section] === isDirty ? current : { ...current, [section]: isDirty }));
  }, []);
  const sections = useMemo(() => Object.keys(dirty).filter((s) => dirty[s]), [dirty]);

  useEffect(() => {
    if (!sections.length) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [sections.length]);

  const value = useMemo(() => ({ report, sections }), [report, sections]);
  return <UnsavedContext.Provider value={value}>{children}</UnsavedContext.Provider>;
}

export function useReportUnsaved(section: string, dirty: boolean) {
  const { report } = useContext(UnsavedContext);
  useEffect(() => {
    report(section, dirty);
    return () => report(section, false);
  }, [section, dirty, report]);
}

export function useUnsavedSections(): string[] {
  return useContext(UnsavedContext).sections;
}
