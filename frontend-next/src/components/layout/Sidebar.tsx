"use client";

import { useCallback, useEffect, useState } from "react";
import type { LegacyRef, RefObject } from "react";
import { ChevronLeft, ChevronRight, Files } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { PdfUpload, type PdfUploadHandle } from "@/components/upload/PdfUpload";
import { DocumentList } from "@/components/documents/DocumentList";
import type { DocumentListItem } from "@/lib/api";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "dashboard-sidebar-collapsed";

function persistCollapsed(collapsed: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    /* ignore */
  }
}

export interface DashboardSidebarProps {
  token: string;
  onSaveComplete: () => void;
  documents: DocumentListItem[];
  documentsLoading: boolean;
  onSelectDocument: (doc: DocumentListItem) => void;
  selectedDocumentName: string | null;
  uploadRef: RefObject<PdfUploadHandle | null>;
  /** Full-width, always expanded; no collapse control (mobile tab panel). */
  mobileMode?: boolean;
}

export function DashboardSidebar({
  token,
  onSaveComplete,
  documents,
  documentsLoading,
  onSelectDocument,
  selectedDocumentName,
  uploadRef,
  mobileMode = false,
}: DashboardSidebarProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    try {
      const v = localStorage.getItem(STORAGE_KEY);
      setCollapsed(v === "1");
    } catch {
      /* ignore */
    }
    setMounted(true);
  }, []);

  const setCollapsedPersist = useCallback((next: boolean) => {
    setCollapsed(next);
    persistCollapsed(next);
  }, []);

  const toggle = () => {
    setCollapsedPersist(!collapsed);
  };

  const expandForUpload = useCallback(() => {
    setCollapsed(false);
    persistCollapsed(false);
  }, []);

  const compact = mobileMode ? false : Boolean(collapsed && mounted);

  return (
    <TooltipProvider delayDuration={300}>
      <aside
        className={cn(
          "sidebar-surface flex min-h-0 min-w-0 flex-col",
          mobileMode
            ? "w-full"
            : collapsed
              ? "w-[var(--sidebar-collapsed-width)]"
              : "w-[var(--sidebar-width)]"
        )}
      >
        <div
          className={cn(
            "flex min-h-0 flex-1 flex-col gap-6 py-6",
            compact ? "items-center px-2" : "px-4"
          )}
        >
          <section className={cn("w-full space-y-2", compact && "flex flex-col items-center")}>
            {!compact && (
              <h2 className="font-heading border-l-2 border-primary/70 pl-2 text-sm font-semibold tracking-tight text-foreground">
                Upload &amp; process
              </h2>
            )}
            <div className={cn(compact && "flex justify-center")}>
              <PdfUpload
                ref={uploadRef as LegacyRef<PdfUploadHandle>}
                token={token}
                onSaveComplete={onSaveComplete}
                compact={compact}
                onExpandForUpload={expandForUpload}
              />
            </div>
          </section>

          {compact && (
            <>
              <Separator className="w-8 shrink-0 bg-border" />
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-muted/30 text-muted-foreground">
                    <Files className="h-4 w-4" aria-hidden />
                  </span>
                </TooltipTrigger>
                <TooltipContent side="right">Documents</TooltipContent>
              </Tooltip>
            </>
          )}

          <DocumentList
            documents={documents}
            isLoading={documentsLoading}
            onSelect={onSelectDocument}
            selectedDocumentName={selectedDocumentName}
            collapsed={compact}
          />
        </div>

        {!mobileMode && (
          <div
            className={cn(
              "mt-auto border-t border-border pt-3 pb-4",
              collapsed ? "flex justify-center px-2" : "px-4"
            )}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-9 w-9 shrink-0 text-muted-foreground hover:text-foreground"
                  onClick={toggle}
                  aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                >
                  {collapsed ? (
                    <ChevronRight className="h-4 w-4" />
                  ) : (
                    <ChevronLeft className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">{collapsed ? "Expand" : "Collapse"}</TooltipContent>
            </Tooltip>
          </div>
        )}
      </aside>
    </TooltipProvider>
  );
}
