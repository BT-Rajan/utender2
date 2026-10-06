import type { DocumentCategory } from "@/api/types";

// Stage 3.6: requirement document types (keys match DOCUMENT_CATEGORIES in
// backend/app/services/drawings.py; labels in the "documents" dictionary).
export const DOCUMENT_CATEGORIES: DocumentCategory[] = ["drawing", "boq", "specification", "photo", "site", "other"];

export const DOCUMENT_ACCEPT = ".pdf,.dwg,.xlsx,.docx,.jpg,.jpeg,.png,.zip";

// Essential documents first, then by type, then by name.
export function sortDocuments<T extends { is_required: boolean; category: DocumentCategory; file_name: string }>(docs: T[]): T[] {
  return [...docs].sort(
    (a, b) =>
      Number(b.is_required) - Number(a.is_required) ||
      DOCUMENT_CATEGORIES.indexOf(a.category) - DOCUMENT_CATEGORIES.indexOf(b.category) ||
      a.file_name.localeCompare(b.file_name),
  );
}
