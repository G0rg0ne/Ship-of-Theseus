"use client";

import Link from "next/link";
import {
  ArrowLeft,
  BookOpen,
  Brain,
  FileUp,
  GitBranch,
  LayoutDashboard,
  LogIn,
  MessageSquare,
  Network,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

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

const pipelineSteps = [
  {
    step: 1,
    title: "Upload",
    body: "Drop a PDF in the sidebar. The app ingests text, chunks it, and prepares it for extraction.",
  },
  {
    step: 2,
    title: "Extract entities & relations",
    body: "An LLM pulls out people, organisations, concepts, and how they connect — the raw material for your graph.",
  },
  {
    step: 3,
    title: "Build community graph",
    body: "After you add a document to your brain, Louvain-style community detection groups related ideas; summaries and embeddings are stored for search.",
  },
  {
    step: 4,
    title: "Explore & ask",
    body: "Switch between document and brain views, watch the graph update, and chat with retrieval tailored to your library.",
  },
];

const features = [
  {
    title: "Document upload",
    icon: FileUp,
    body: (
      <>
        <p>
          Use the left sidebar to upload a PDF. You&apos;ll see processing steps
          (chunking, extraction, preview) before you confirm{" "}
          <strong className="text-foreground">Add to Brain</strong>. That saves
          the graph to Neo4j and kicks off the full GraphRAG pipeline in the
          background — community detection, LLM summaries per community, and
          vector embeddings for semantic search.
        </p>
      </>
    ),
  },
  {
    title: "Knowledge graph (per document)",
    icon: Network,
    body: (
      <>
        <p>
          Pick a document from the list to open the{" "}
          <strong className="text-foreground">Document graph</strong> tab. Nodes
          are entities; edges are relationships extracted from that file. The
          force-directed layout lets you pan, zoom, and explore how concepts link
          in real time.
        </p>
      </>
    ),
  },
  {
    title: "Brain graph (across documents)",
    icon: Brain,
    body: (
      <>
        <p>
          The <strong className="text-foreground">Brain graph</strong> merges
          everything you&apos;ve added into one knowledge brain. Communities
          appear as clusters; open the community panel to read LLM-generated
          summaries from leaf level up to root themes. Refresh pulls the latest
          persisted state from the server without re-running detection.
        </p>
      </>
    ),
  },
  {
    title: "Chat & Q&A",
    icon: MessageSquare,
    body: (
      <>
        <p>
          The right-hand <strong className="text-foreground">Ask your brain</strong>{" "}
          panel is your GraphRAG interface. Your question triggers vector search
          over entities and community summaries, pulls the most relevant context,
          and streams an answer grounded in your documents — not generic web
          knowledge.
        </p>
        <p className="mt-2">
          You can scope context with document badges so answers stay focused on
          specific sources when you want tighter, tailored replies.
        </p>
      </>
    ),
  },
  {
    title: "Real-time visualization",
    icon: GitBranch,
    body: (
      <>
        <p>
          Graphs use a live force simulation: nodes settle as data loads, and
          when you upload new material or refresh the brain, the visualization
          updates to reflect new entities, relationships, and communities.
        </p>
        <p className="mt-2">
          Pipeline progress (detection → summarization → embedding) is
          surfaced in the UI so you can see your brain evolving while you work.
        </p>
      </>
    ),
  },
];

const quickStart = [
  "Upload a PDF from the left sidebar and wait for extraction to finish.",
  "Review the per-document graph preview, then click Add to Brain.",
  "Wait for the GraphRAG pipeline to complete (progress appears in the upload area).",
  "Switch to Brain graph to see your merged knowledge and community summaries.",
  "Ask a question in the chat panel — optionally tag specific documents for narrower answers.",
];

export default function HowItWorksPage() {
  const { token, isLoading: authLoading } = useAuth();
  const isAuthed = Boolean(token);

  if (authLoading) {
    return (
      <main className="h-screen overflow-hidden flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </main>
    );
  }

  const homeHref = isAuthed ? "/dashboard" : "/";
  const backLabel = isAuthed ? "Back to dashboard" : "Back to sign in";
  const backHref = isAuthed ? "/dashboard" : "/";

  return (
    <div className="min-h-screen flex flex-col bg-background bg-dot-grid">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div
          className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent"
          aria-hidden
        />
        <div className="w-full relative flex h-14 items-center justify-between px-4 sm:px-6">
          <Link
            href={homeHref}
            className="flex items-center gap-2.5 font-heading font-semibold text-foreground transition-opacity hover:opacity-90"
          >
            <AnchorIcon className="h-6 w-6 text-primary" />
            <span>Ship of Theseus</span>
          </Link>
          <Button variant="outline" size="sm" className="gap-2" asChild>
            <Link href={backHref}>
              <ArrowLeft className="h-3.5 w-3.5" />
              {backLabel}
            </Link>
          </Button>
        </div>
      </header>

      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-6 py-10 sm:py-14 space-y-14">
        {/* Hero */}
        <section className="space-y-4 text-center sm:text-left">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            <Sparkles className="h-3.5 w-3.5" aria-hidden />
            Guide
          </div>
          <h1 className="font-heading text-3xl sm:text-4xl font-semibold tracking-tight text-foreground">
            How Ship of Theseus works
          </h1>
          <p className="text-muted-foreground text-base max-w-2xl mx-auto sm:mx-0">
            Turn PDFs into a living knowledge graph, then ask questions that pull
            answers from <em>your</em> documents — with graphs and communities
            updating as your library grows.
          </p>
          <div className="flex flex-wrap gap-3 justify-center sm:justify-start pt-2">
            {isAuthed ? (
              <Button className="gap-2" asChild>
                <Link href="/dashboard">
                  <LayoutDashboard className="h-4 w-4" />
                  Open dashboard
                </Link>
              </Button>
            ) : (
              <Button className="gap-2" asChild>
                <Link href="/">
                  <LogIn className="h-4 w-4" />
                  Sign up or sign in
                </Link>
              </Button>
            )}
          </div>
        </section>

        {/* Pipeline strip */}
        <section aria-labelledby="pipeline-heading" className="space-y-4">
          <h2
            id="pipeline-heading"
            className="font-heading text-lg font-semibold text-foreground"
          >
            The pipeline
          </h2>
          <div className="flex gap-4 overflow-x-auto pb-2 -mx-1 px-1 snap-x snap-mandatory">
            {pipelineSteps.map((s) => (
              <article
                key={s.step}
                className="snap-start shrink-0 w-[min(100%,280px)] rounded-xl border border-border bg-card/60 backdrop-blur p-4 border-l-4 border-l-primary"
              >
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-primary/15 text-sm font-bold text-primary">
                  {s.step}
                </span>
                <h3 className="mt-3 font-heading font-semibold text-foreground">
                  {s.title}
                </h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                  {s.body}
                </p>
              </article>
            ))}
          </div>
        </section>

        {/* Feature deep-dives */}
        <section aria-labelledby="features-heading" className="space-y-10">
          <h2
            id="features-heading"
            className="font-heading text-lg font-semibold text-foreground"
          >
            Features in the dashboard
          </h2>
          <ul className="space-y-12 list-none p-0 m-0">
            {features.map((f, i) => {
              const Icon = f.icon;
              const reverse = i % 2 === 1;
              return (
                <li
                  key={f.title}
                  className={[
                    "grid gap-6 sm:gap-8 sm:grid-cols-2 sm:items-center",
                    reverse ? "sm:[&>div:first-child]:order-2" : "",
                  ].join(" ")}
                >
                  <div
                    className={[
                      "rounded-xl border border-border bg-card/60 backdrop-blur p-6 flex items-center justify-center min-h-[140px]",
                      "bg-gradient-to-br from-primary/5 to-transparent",
                    ].join(" ")}
                  >
                    <Icon
                      className="h-16 w-16 text-primary/80"
                      strokeWidth={1.25}
                      aria-hidden
                    />
                  </div>
                  <div className="space-y-3">
                    <h3 className="font-heading text-xl font-semibold text-foreground flex items-center gap-2">
                      <BookOpen className="h-5 w-5 text-primary shrink-0" />
                      {f.title}
                    </h3>
                    <div className="text-sm text-muted-foreground space-y-2 leading-relaxed">
                      {f.body}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        {/* Quick start */}
        <section
          aria-labelledby="quickstart-heading"
          className="rounded-xl border border-border bg-card/60 backdrop-blur p-6 sm:p-8"
        >
          <h2
            id="quickstart-heading"
            className="font-heading text-lg font-semibold text-foreground mb-4"
          >
            Quick start
          </h2>
          <ol className="list-decimal list-inside space-y-3 text-sm text-muted-foreground marker:text-primary marker:font-semibold">
            {quickStart.map((line) => (
              <li key={line} className="pl-1">
                <span className="text-muted-foreground">{line}</span>
              </li>
            ))}
          </ol>
        </section>

        {/* Footer CTA */}
        <footer className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-8 border-t border-border pt-10">
          <p className="font-heading text-base font-medium text-foreground">
            {isAuthed ? "Ready to explore?" : "Ready to build your brain?"}
          </p>
          <Button asChild>
            <Link href={isAuthed ? "/dashboard" : "/"}>
              {isAuthed ? "Return to dashboard" : "Get started"}
            </Link>
          </Button>
        </footer>
      </main>
    </div>
  );
}
