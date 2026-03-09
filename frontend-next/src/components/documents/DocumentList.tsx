"use client";

import type { DocumentListItem } from "@/lib/api";

function PdfIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <path d="M9 13h6" />
      <path d="M9 17h6" />
      <path d="M9 9h1" />
    </svg>
  );
}

interface DocumentListProps {
  documents: DocumentListItem[];
  isLoading?: boolean;
  onSelect?: (doc: DocumentListItem) => void;
  selectedDocumentName?: string | null;
}

export function DocumentList({
  documents,
  isLoading,
  onSelect,
  selectedDocumentName,
}: DocumentListProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground">Documents</h3>
        <div className="rounded-lg border border-border bg-muted/30 px-3 py-4 text-center text-sm text-muted-foreground">
          Loading…
        </div>
      </div>
    );
  }

  if (!documents?.length) {
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground">Documents</h3>
        <div className="rounded-lg border border-border bg-muted/30 px-3 py-4 text-center text-sm text-muted-foreground">
          No documents yet. Upload a PDF to begin.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-foreground">Documents</h3>
      <ul className="flex flex-col gap-1 overflow-auto rounded-lg border border-border bg-muted/30 p-2 max-h-[200px] min-h-0">
        {documents.map((doc) => (
          <li
            key={doc.document_name}
            onClick={() => onSelect?.(doc)}
            className={[
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm text-foreground hover:bg-background/60 cursor-pointer",
              selectedDocumentName === doc.document_name
                ? "bg-background/70 border border-border/70"
                : "",
            ].join(" ")}
          >
            <PdfIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate" title={doc.document_name}>
              {doc.document_name}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
