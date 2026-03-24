"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { FolderOpen, MessageSquare, Network } from "lucide-react";
import { BrainSection } from "@/components/brain/BrainSection";
import { ChatSection } from "@/components/chat/ChatSection";
import { DocumentGraphView } from "@/components/upload/DocumentGraphView";
import { DashboardHeader } from "@/components/layout/Header";
import { DashboardSidebar } from "@/components/layout/Sidebar";
import type { PdfUploadHandle } from "@/components/upload/PdfUpload";
import { useAuth } from "@/hooks/useAuth";
import { useBrain } from "@/hooks/useBrain";
import * as api from "@/lib/api";
import type { DocumentListItem } from "@/lib/api";
import { cn } from "@/lib/utils";

type MobileTab = "files" | "graph" | "chat";

export default function DashboardPage() {
  const router = useRouter();
  const { token, user, isLoading: authLoading, logout } = useAuth();
  const { brain, isLoading: brainLoading, mutate: mutateBrain } = useBrain(token);
  const uploadRef = useRef<PdfUploadHandle | null>(null);

  useEffect(() => {
    if (!authLoading && !token) {
      router.replace("/");
    }
  }, [token, authLoading, router]);

  const handleLogout = async () => {
    await logout();
    router.replace("/");
  };

  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<DocumentListItem | null>(null);
  const [selectedDocumentGraph, setSelectedDocumentGraph] = useState<api.DocumentGraph | null>(null);
  const [centerTab, setCenterTab] = useState<"document" | "brain">("brain");
  const [mobileTab, setMobileTab] = useState<MobileTab>("graph");

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
      setMobileTab("graph");
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
    setGreeting(hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening");
  }, []);

  const centerViewLabel = centerTab === "document" ? "Document graph" : "Brain graph";

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.06, delayChildren: 0.04 },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 8 },
    show: { opacity: 1, y: 0, transition: { duration: 0.25 } },
  };

  const chatProps = {
    documents,
    token,
    brain,
    brainLoading,
  };

  if (authLoading || !token) {
    return (
      <main className="flex h-screen items-center justify-center overflow-hidden bg-background">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </main>
    );
  }

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-background bg-dot-grid">
      <DashboardHeader
        displayName={displayName}
        greeting={greeting}
        email={user?.email ?? null}
        initials={initials}
        isAdmin={user?.is_admin}
        centerViewLabel={centerViewLabel}
        onLogout={handleLogout}
        onMobileFilesOpen={() => setMobileTab("files")}
      />

      <motion.div
        className="flex min-h-0 flex-1 w-full flex-col lg:flex-row"
        variants={containerVariants}
        initial="hidden"
        animate="show"
      >
        {/* Desktop: sidebar | graph | chat */}
        <div className="hidden min-h-0 flex-1 lg:flex">
          <motion.div variants={itemVariants} className="flex min-h-0 shrink-0">
            <DashboardSidebar
              token={token}
              onSaveComplete={handleSaveComplete}
              documents={documents}
              documentsLoading={documentsLoading}
              onSelectDocument={handleSelectDocument}
              selectedDocumentName={selectedDocument?.document_name ?? null}
              uploadRef={uploadRef}
            />
          </motion.div>

          <motion.div
            variants={itemVariants}
            className="min-w-0 flex-1 overflow-auto border-r border-border"
          >
            <div className="flex h-full min-h-0 flex-col space-y-4 px-4 py-6">
              <div className="relative flex w-full max-w-md rounded-full border border-border bg-muted/40 p-1 text-sm">
                <motion.div
                  className="pointer-events-none absolute top-1 bottom-1 left-1 w-[calc(50%-6px)] rounded-full bg-background shadow-sm"
                  initial={false}
                  animate={{
                    x: centerTab === "document" ? 0 : "calc(100% + 4px)",
                  }}
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
                <button
                  type="button"
                  onClick={() => setCenterTab("document")}
                  className={cn(
                    "relative z-10 flex flex-1 items-center justify-center gap-1.5 rounded-full px-3 py-2.5 text-xs font-medium transition-colors sm:text-sm",
                    centerTab === "document"
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Network className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
                  Document graph
                </button>
                <button
                  type="button"
                  onClick={() => setCenterTab("brain")}
                  className={cn(
                    "relative z-10 flex flex-1 items-center justify-center gap-1.5 rounded-full px-3 py-2.5 text-xs font-medium transition-colors sm:text-sm",
                    centerTab === "brain"
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  Brain graph
                </button>
              </div>

              <AnimatePresence mode="wait">
                {centerTab === "document" ? (
                  <motion.div
                    key="doc"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                    className="min-h-0 flex-1"
                  >
                    <DocumentGraphView graph={selectedDocumentGraph} communities={null} />
                  </motion.div>
                ) : (
                  <motion.div
                    key="brain"
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.2 }}
                    className="min-h-0 flex-1"
                  >
                    <BrainSection
                      token={token}
                      onBrainCleared={() => {
                        setDocuments([]);
                        setSelectedDocument(null);
                        setSelectedDocumentGraph(null);
                      }}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>

          <motion.aside
            variants={itemVariants}
            className="flex min-h-0 w-[380px] min-w-[320px] shrink-0 flex-col overflow-hidden border-border bg-background/50"
          >
            <ChatSection {...chatProps} />
          </motion.aside>
        </div>

        {/* Mobile: one tab at a time + bottom nav */}
        <div className="flex min-h-0 flex-1 flex-col lg:hidden">
          <div className="relative min-h-0 flex-1 overflow-hidden">
            {mobileTab === "files" && (
              <div className="flex h-full min-h-0 flex-col overflow-y-auto">
                <DashboardSidebar
                  token={token}
                  onSaveComplete={handleSaveComplete}
                  documents={documents}
                  documentsLoading={documentsLoading}
                  onSelectDocument={handleSelectDocument}
                  selectedDocumentName={selectedDocument?.document_name ?? null}
                  uploadRef={uploadRef}
                  mobileMode
                />
              </div>
            )}
            {mobileTab === "graph" && (
              <div className="flex h-full min-h-0 flex-col overflow-auto border-border">
                <div className="flex h-full min-h-0 flex-col space-y-4 px-4 py-6">
                  <div className="relative flex w-full max-w-md rounded-full border border-border bg-muted/40 p-1 text-sm">
                    <motion.div
                      className="pointer-events-none absolute top-1 bottom-1 left-1 w-[calc(50%-6px)] rounded-full bg-background shadow-sm"
                      initial={false}
                      animate={{
                        x: centerTab === "document" ? 0 : "calc(100% + 4px)",
                      }}
                      transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    />
                    <button
                      type="button"
                      onClick={() => setCenterTab("document")}
                      className={cn(
                        "relative z-10 flex flex-1 items-center justify-center gap-1.5 rounded-full px-3 py-2.5 text-xs font-medium transition-colors sm:text-sm",
                        centerTab === "document"
                          ? "text-foreground"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <Network className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
                      Document graph
                    </button>
                    <button
                      type="button"
                      onClick={() => setCenterTab("brain")}
                      className={cn(
                        "relative z-10 flex flex-1 items-center justify-center gap-1.5 rounded-full px-3 py-2.5 text-xs font-medium transition-colors sm:text-sm",
                        centerTab === "brain"
                          ? "text-foreground"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      Brain graph
                    </button>
                  </div>

                  <AnimatePresence mode="wait">
                    {centerTab === "document" ? (
                      <motion.div
                        key="doc-m"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        transition={{ duration: 0.2 }}
                        className="min-h-0 flex-1"
                      >
                        <DocumentGraphView graph={selectedDocumentGraph} communities={null} />
                      </motion.div>
                    ) : (
                      <motion.div
                        key="brain-m"
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -6 }}
                        transition={{ duration: 0.2 }}
                        className="min-h-0 flex-1"
                      >
                        <BrainSection
                          token={token}
                          onBrainCleared={() => {
                            setDocuments([]);
                            setSelectedDocument(null);
                            setSelectedDocumentGraph(null);
                          }}
                        />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </div>
            )}
            {mobileTab === "chat" && (
              <div className="flex h-full min-h-0 flex-col overflow-hidden bg-background/50">
                <ChatSection {...chatProps} />
              </div>
            )}
          </div>

          <nav
            className="flex shrink-0 items-stretch border-t border-border bg-background/95 pb-[max(0.5rem,env(safe-area-inset-bottom))] backdrop-blur supports-[backdrop-filter]:bg-background/80"
            aria-label="Dashboard sections"
          >
            {(
              [
                { id: "files" as const, icon: FolderOpen, label: "Files" },
                { id: "graph" as const, icon: Network, label: "Graph" },
                { id: "chat" as const, icon: MessageSquare, label: "Chat" },
              ] as const
            ).map(({ id, icon: Icon, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setMobileTab(id)}
                className={cn(
                  "flex flex-1 flex-col items-center justify-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors",
                  mobileTab === id ? "text-primary" : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-5 w-5 shrink-0" aria-hidden />
                {label}
              </button>
            ))}
          </nav>
        </div>
      </motion.div>
    </main>
  );
}
