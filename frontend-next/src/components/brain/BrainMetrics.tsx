"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { UserBrain } from "@/lib/api";

interface BrainMetricsProps {
  brain: UserBrain | null;
  isLoading?: boolean;
}

export function BrainMetrics({ brain, isLoading }: BrainMetricsProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} variant="accent">
            <CardContent className="p-4">
              <div className="h-4 w-16 animate-pulse rounded bg-muted" />
              <div className="mt-1 h-6 w-8 animate-pulse rounded bg-muted" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!brain) {
    return (
      <p className="text-sm text-muted-foreground">
        No knowledge brain yet. Add documents to the knowledge base to build it.
      </p>
    );
  }

  const metrics = [
    { label: "Documents", value: brain.document_count },
    { label: "Total entities", value: brain.total_nodes },
    { label: "Relationships", value: brain.total_edges },
    { label: "Communities", value: brain.community_count },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map(({ label, value }) => (
        <Card key={label} variant="accent">
          <CardContent className="p-4">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
            <p className="font-heading text-2xl font-bold text-foreground mt-1">{value}</p>
          </CardContent>
        </Card>
      ))}
      {brain.last_updated && (
        <p className="col-span-full text-xs text-muted-foreground">
          Last updated: {new Date(brain.last_updated).toLocaleString()}
        </p>
      )}
    </div>
  );
}
