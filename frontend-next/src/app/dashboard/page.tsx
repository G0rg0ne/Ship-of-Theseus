"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { PdfUpload } from "@/components/upload/PdfUpload";
import { BrainSection } from "@/components/brain/BrainSection";
import { ChatSection } from "@/components/chat/ChatSection";
import { DocumentList } from "@/components/documents/DocumentList";
import { DocumentGraphView } from "@/components/upload/DocumentGraphView";
import { useAuth } from "@/hooks/useAuth";
import { useBrain } from "@/hooks/useBrain";
import * as api from "@/lib/api";
import type { DocumentListItem } from "@/lib/api";

function AnchorIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 22V8" />
      <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
      <circle cx="12" cy="5" r="3" />
    </svg>
  );
}

function LogOutIcon({ className }: { className?: string }) {
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
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" x2="9" y1="12" y2="12" />
    </svg>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const { token, user, isLoading: authLoading, logout } = useAuth();
  const { mutate: mutateBrain } = useBrain(token);

  useEffect(() => {
    if (!authLoading && !token) {
      router.replace("/");
    }
  }, [token, authLoading, router]);

  const handleLogout = () => {
    logout();
    router.replace("/");
  };

  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<DocumentListItem | null>(null);
  const [selectedDocumentGraph, setSelectedDocumentGraph] = useState<api.DocumentGraph | null>(null);
  const [centerTab, setCenterTab] = useState<"document" | "brain">("brain");

  const loadDocuments = useCallback(async () => {
    if (!token) return;
    setDocumentsLoading(true);
    try {
      const list = await api.listNeo4jDocuments(token);
      setDocuments(list);
    } catch {
      setDocuments([]);
    } finally {
      setDocumentsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const handleSaveComplete = () => {
    mutateBrain();
    loadDocuments();
  };

  const handleSelectDocument = useCallback(
    async (doc: DocumentListItem) => {
      if (!token) return;
      setSelectedDocument(doc);
      setCenterTab("document");
      try {
        const g = await api.getGraphFromNeo4j(doc.document_name, token);
        setSelectedDocumentGraph(g);
      } catch {
        setSelectedDocumentGraph(null);
      }
    },
    [token]
  );

  const rawName = user?.username ?? user?.email ?? "User";
  const displayName = rawName.includes("@") ? rawName.split("@")[0] : rawName;
  const initials =
    displayName.length >= 2
      ? displayName.slice(0, 2).toUpperCase()
      : displayName.slice(0, 1).toUpperCase() || "U";

  const [greeting, setGreeting] = useState("Welcome");
  useEffect(() => {
    const hour = new Date().getHours();
    setGreeting(
      hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening"
    );
  }, []);

  if (authLoading || !token) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex flex-col bg-background bg-dot-grid">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div
          className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent"
          aria-hidden
        />
        <div className="w-full relative flex h-14 items-center justify-between px-4 sm:px-6">
          <Link
            href="/dashboard"
            className="flex items-center gap-2.5 font-heading font-semibold text-foreground transition-opacity hover:opacity-90"
          >
            <AnchorIcon className="h-6 w-6 text-primary" />
            <span>Ship of Theseus</span>
          </Link>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
                {initials}
              </span>
              <span className="text-sm font-medium text-foreground">
                {displayName}
              </span>
            </div>
            <div className="h-4 w-px bg-border" aria-hidden />
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="gap-1.5 text-muted-foreground hover:text-foreground"
            >
              <LogOutIcon className="h-3.5 w-3.5" />
              Log out
            </Button>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)_380px] flex-1 min-h-0 w-full">
        {/* Left sidebar: greeting, upload, document list */}
        <aside className="min-w-0 overflow-auto border-r border-border bg-background/50">
          <div className="flex flex-col gap-6 px-4 py-6">
            <div>
              <h1 className="font-heading text-lg font-semibold text-foreground">
                {greeting}, {displayName}
              </h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                Documents & knowledge graph.
              </p>
            </div>
            <section className="space-y-2">
              <h2 className="font-heading text-sm font-semibold tracking-tight text-foreground pl-2 border-l-2 border-primary/70">
                Upload & process
              </h2>
              <PdfUpload token={token} onSaveComplete={handleSaveComplete} />
            </section>
            <DocumentList
              documents={documents}
              isLoading={documentsLoading}
              onSelect={handleSelectDocument}
              selectedDocumentName={selectedDocument?.document_name ?? null}
            />
          </div>
        </aside>

        {/* Center: document graph vs brain graph */}
        <div className="min-w-0 overflow-auto border-r border-border">
          <div className="h-full flex flex-col px-4 py-6 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex gap-1 rounded-full border border-border bg-muted/40 p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setCenterTab("document")}
                  className={[
                    "px-2.5 py-1 rounded-full transition-colors",
                    centerTab === "document"
                      ? "bg-background text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  Document graph
                </button>
                <button
                  type="button"
                  onClick={() => setCenterTab("brain")}
                  className={[
                    "px-2.5 py-1 rounded-full transition-colors",
                    centerTab === "brain"
                      ? "bg-background text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  Brain graph
                </button>
              </div>
            </div>

            {centerTab === "document" ? (
              <DocumentGraphView graph={selectedDocumentGraph} communities={null} />
            ) : (
              <BrainSection
                token={token}
                onBrainCleared={() => {
                  setDocuments([]);
                  setSelectedDocument(null);
                  setSelectedDocumentGraph(null);
                }}
              />
            )}
          </div>
        </div>

        {/* Right panel: chat */}
        <aside className="hidden lg:flex flex-col min-w-0 min-h-0 border-border bg-background/50 overflow-hidden">
          <ChatSection documents={documents} />
        </aside>
      </div>
    </main>
  );
}
