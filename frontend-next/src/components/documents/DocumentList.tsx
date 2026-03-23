"use client";

import { FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { DocumentListItem } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DocumentListProps {
  documents: DocumentListItem[];
  isLoading?: boolean;
  onSelect?: (doc: DocumentListItem) => void;
  selectedDocumentName?: string | null;
  collapsed?: boolean;
}

export function DocumentList({
  documents,
  isLoading,
  onSelect,
  selectedDocumentName,
  collapsed = false,
}: DocumentListProps) {
  if (isLoading) {
    if (collapsed) {
      return (
        <TooltipProvider delayDuration={300}>
          <div className="flex justify-center py-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex h-10 w-10 items-center justify-center rounded-md border border-border bg-muted/30">
                  <Skeleton className="h-5 w-5 rounded" />
                </div>
              </TooltipTrigger>
              <TooltipContent side="right">Loading documents…</TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
      );
    }
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground">Documents</h3>
        <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-[83%]" />
        </div>
      </div>
    );
  }

  if (!documents?.length) {
    if (collapsed) {
      return (
        <TooltipProvider delayDuration={300}>
          <div className="flex justify-center py-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <div
                  className="flex h-10 w-10 cursor-default items-center justify-center rounded-md border border-dashed border-border/70 bg-muted/20 text-muted-foreground"
                  aria-label="No documents"
                >
                  <FileText className="h-4 w-4 opacity-60" aria-hidden />
                </div>
              </TooltipTrigger>
              <TooltipContent side="right" className="max-w-xs">
                <p className="font-medium">No documents yet</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Expand the sidebar and use Upload to add a PDF, or click the upload icon.
                </p>
              </TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
      );
    }
    return (
      <div className="space-y-2">
        <h3 className="text-sm font-medium text-foreground">Documents</h3>
        <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border/80 bg-muted/20 px-4 py-8 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <FileText className="h-6 w-6" aria-hidden />
          </div>
          <p className="text-sm font-medium text-foreground">No documents yet</p>
          <p className="max-w-[200px] text-xs text-muted-foreground">
            Upload a PDF in the panel above to build your knowledge graph.
          </p>
        </div>
      </div>
    );
  }

  if (collapsed) {
    return (
      <TooltipProvider delayDuration={300}>
        <ScrollArea className="h-[min(200px,40vh)] w-full pr-1">
          <ul className="flex flex-col items-center gap-1.5 py-1">
            {documents.map((doc) => {
              const selected = selectedDocumentName === doc.document_name;
              return (
                <li key={doc.document_name}>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        type="button"
                        onClick={() => onSelect?.(doc)}
                        className={cn(
                          "flex h-10 w-10 items-center justify-center rounded-md border transition-colors",
                          selected
                            ? "border-primary/50 bg-primary/15 text-primary shadow-[0_0_12px_-4px_hsl(var(--primary)/0.5)]"
                            : "border-border bg-muted/40 text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                        )}
                        aria-label={doc.document_name}
                      >
                        <FileText className="h-4 w-4 shrink-0" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-xs">
                      <p className="font-medium break-all">{doc.document_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {doc.node_count} nodes · {doc.edge_count} edges
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </li>
              );
            })}
          </ul>
        </ScrollArea>
      </TooltipProvider>
    );
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-foreground">Documents</h3>
      <ScrollArea className="h-[min(200px,40vh)] rounded-lg border border-border bg-muted/30">
        <ul className="flex flex-col gap-1 p-2">
          {documents.map((doc) => {
            const selected = selectedDocumentName === doc.document_name;
            return (
              <li key={doc.document_name}>
                <button
                  type="button"
                  onClick={() => onSelect?.(doc)}
                  className={cn(
                    "flex w-full items-start gap-2 rounded-md px-2 py-2 text-left text-sm text-foreground transition-colors",
                    "hover:bg-background/60",
                    selected &&
                      "relative bg-background/80 shadow-sm ring-1 ring-border/80 before:absolute before:left-0 before:top-1 before:bottom-1 before:w-0.5 before:rounded-full before:bg-primary"
                  )}
                >
                  <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1 truncate font-medium" title={doc.document_name}>
                    {doc.document_name}
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-0.5">
                    <Badge variant="muted" className="tabular-nums text-[10px] font-normal">
                      {doc.node_count}n
                    </Badge>
                    <Badge variant="outline" className="tabular-nums text-[10px] font-normal">
                      {doc.edge_count}e
                    </Badge>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </ScrollArea>
    </div>
  );
}
