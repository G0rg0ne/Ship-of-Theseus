"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { PdfUpload } from "@/components/upload/PdfUpload";
import { BrainSection } from "@/components/brain/BrainSection";
import { useAuth } from "@/hooks/useAuth";
import { useBrain } from "@/hooks/useBrain";

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

  const handleSaveComplete = () => {
    mutateBrain();
  };

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
    <main className="min-h-screen bg-background bg-dot-grid">
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

      <div className="container max-w-5xl space-y-12 px-4 py-10">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-heading text-2xl font-semibold text-foreground">
              {greeting}, {displayName}
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Manage your documents and explore your knowledge graph.
            </p>
          </div>
        </div>

        <section className="space-y-4">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-foreground pl-3 border-l-2 border-primary/70">
            Upload & process
          </h2>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Upload a PDF to extract entities and relationships, then add the
            graph to your knowledge base.
          </p>
          <PdfUpload token={token} onSaveComplete={handleSaveComplete} />
        </section>

        <section className="space-y-4">
          <h2 className="font-heading text-xl font-semibold tracking-tight text-foreground pl-3 border-l-2 border-primary/70">
            Your knowledge brain
          </h2>
          <p className="text-sm text-muted-foreground max-w-2xl">
            View your merged knowledge graph and communities. Click a node to see
            its community details.
          </p>
          <BrainSection token={token} />
        </section>
      </div>
    </main>
  );
}
