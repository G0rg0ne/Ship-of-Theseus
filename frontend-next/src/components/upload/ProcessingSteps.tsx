"use client";

import { Progress } from "@/components/ui/progress";
import type { ProcessingProgress } from "@/hooks/useUpload";

interface ProcessingStepsProps {
  progress: ProcessingProgress | null;
  entityCount?: number;
  relationshipCount?: number;
}

export function ProcessingSteps({
  progress,
  entityCount,
  relationshipCount,
}: ProcessingStepsProps) {
  if (!progress) return null;

  const pct =
    progress.total > 0
      ? Math.round((progress.completed / progress.total) * 100)
      : 0;
  const displayPct = Math.min(100, Math.max(0, pct));

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">{progress.message}</p>
      <Progress value={displayPct} className="h-2" />
      {entityCount != null && relationshipCount != null && (
        <div className="mt-2 flex gap-4 text-sm">
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
