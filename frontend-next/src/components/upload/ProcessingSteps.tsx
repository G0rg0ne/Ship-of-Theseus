"use client";

import { Progress } from "@/components/ui/progress";
import type { ProcessingProgress, ProcessingState } from "@/hooks/useUpload";

interface ProcessingStepsProps {
  state: ProcessingState;
  progress: ProcessingProgress | null;
  entityCount?: number;
  relationshipCount?: number;
}

const STAGES: { id: ProcessingState; label: string }[] = [
  { id: "uploading", label: "Upload" },
  { id: "extracting_entities", label: "Entities" },
  { id: "extracting_relationships", label: "Relationships" },
  { id: "saving_graph", label: "Saving" },
  { id: "detecting_communities", label: "Communities" },
  { id: "summarizing", label: "Summaries" },
  { id: "embedding", label: "Embeddings" },
];

export function ProcessingSteps({
  state,
  progress,
  entityCount,
  relationshipCount,
}: ProcessingStepsProps) {
  const isPipelineState =
    state === "saving_graph" ||
    state === "detecting_communities" ||
    state === "summarizing" ||
    state === "embedding";

  const fallbackMessage: string | null = (() => {
    switch (state) {
      case "saving_graph":
        return "Saving graph to knowledge base…";
      case "detecting_communities":
        return "Starting brain pipeline…";
      case "summarizing":
        return "Summarizing communities…";
      case "embedding":
        return "Embedding entities and summaries…";
      default:
        return null;
    }
  })();

  // If we're in a long-running pipeline state but the first poll has not
  // yet populated progress, synthesize a minimal progress object so the
  // UI shows a status message instead of an empty header + 0% bar.
  const effectiveProgress: ProcessingProgress | null =
    progress ??
    (isPipelineState && fallbackMessage
      ? {
          completed: 0,
          total: 1,
          message: fallbackMessage,
        }
      : null);

  const rawIndex = STAGES.findIndex((s) => s.id === state);

  const activeIndex =
    state === "preview"
      ? STAGES.findIndex((s) => s.id === "extracting_relationships")
      : state === "done"
      ? STAGES.length
      : rawIndex;

  const pct =
    effectiveProgress && effectiveProgress.total > 0
      ? Math.round((effectiveProgress.completed / effectiveProgress.total) * 100)
      : 0;
  const displayPct = Math.min(100, Math.max(0, pct));

  const showProgressBar =
    effectiveProgress != null && state !== "idle" && state !== "error";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs font-medium text-muted-foreground">
        <span>Processing pipeline</span>
        {effectiveProgress && <span>{effectiveProgress.message}</span>}
      </div>

      <ol className="flex flex-wrap gap-1.5 text-[11px]">
        {STAGES.map((stage, index) => {
          const isCompleted = activeIndex > index;
          const isActive = activeIndex === index;
          return (
            <li
              key={stage.id}
              className="flex items-center gap-1.5 rounded-full border border-border bg-background/80 px-2 py-0.5"
            >
              <span
                className={[
                  "flex h-4 w-4 items-center justify-center rounded-full text-[9px]",
                  isCompleted
                    ? "bg-emerald-500 text-emerald-950"
                    : isActive
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground",
                ].join(" ")}
              >
                {isCompleted ? "✓" : index + 1}
              </span>
              <span
                className={
                  isActive
                    ? "text-foreground"
                    : isCompleted
                    ? "text-muted-foreground"
                    : "text-muted-foreground/70"
                }
              >
                {stage.label}
              </span>
              {isActive &&
                stage.id === "summarizing" &&
                effectiveProgress &&
                effectiveProgress.total > 1 && (
                  <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {effectiveProgress.completed}/{effectiveProgress.total}
                  </span>
                )}
              {isActive && (
                <span className="inline-flex h-3 w-3 items-center justify-center">
                  <span className="h-2 w-2 animate-ping rounded-full bg-primary" />
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {showProgressBar && (
        <Progress value={displayPct} className="h-1.5" />
      )}

      {entityCount != null && relationshipCount != null && (
        <div className="mt-1 flex gap-4 text-xs text-muted-foreground">
          <span>
            <strong>Entities:</strong> {entityCount}
          </span>
          <span>
            <strong>Relationships:</strong> {relationshipCount}
          </span>
        </div>
      )}
    </div>
  );
}
