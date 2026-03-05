"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { PdfUpload } from "@/components/upload/PdfUpload";
import { BrainSection } from "@/components/brain/BrainSection";
import { useAuth } from "@/hooks/useAuth";
import { useBrain } from "@/hooks/useBrain";

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

  if (authLoading || !token) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div
          className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/30 to-transparent"
          aria-hidden
        />
        <div className="container relative flex h-14 items-center justify-between px-4">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 font-semibold text-foreground transition-opacity hover:opacity-90"
          >
            <span className="text-xl" aria-hidden>⚓</span>
            <span>Ship of Theseus</span>
          </Link>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {user?.username ?? user?.email ?? "User"}
            </span>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <div className="container max-w-4xl space-y-10 px-4 py-8">
        <section className="rounded-xl border border-border bg-card/50 p-6">
          <h2 className="mb-2 text-lg font-semibold tracking-tight">
            Upload & process
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Upload a PDF to extract entities and relationships, then add the
            graph to your knowledge base.
          </p>
          <PdfUpload token={token} onSaveComplete={handleSaveComplete} />
        </section>

        <section className="rounded-xl border border-border bg-card/50 p-6">
          <h2 className="mb-2 text-lg font-semibold tracking-tight">
            Your knowledge brain
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            View your merged knowledge graph and communities. Click a node to see
            its community details.
          </p>
          <BrainSection token={token} />
        </section>
      </div>
    </main>
  );
}
