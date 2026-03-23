"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Boxes, FileText, GitFork, Users } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { UserBrain } from "@/lib/api";
import { cn } from "@/lib/utils";

interface BrainMetricsProps {
  brain: UserBrain | null;
  isLoading?: boolean;
}

function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const now = Date.now();
  const diffSec = Math.round((now - d.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (Math.abs(diffSec) < 60) return rtf.format(-diffSec, "second");
  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60) return rtf.format(-diffMin, "minute");
  const diffHr = Math.round(diffMin / 60);
  if (Math.abs(diffHr) < 48) return rtf.format(-diffHr, "hour");
  const diffDay = Math.round(diffHr / 24);
  return rtf.format(-diffDay, "day");
}

function CountUp({ value }: { value: number }) {
  const [display, setDisplay] = useState(0);
  useEffect(() => {
    const steps = 14;
    const duration = 320;
    const stepTime = duration / steps;
    const inc = value / steps;
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setDisplay(Math.min(value, Math.round(inc * i)));
      if (i >= steps) {
        setDisplay(value);
        window.clearInterval(id);
      }
    }, stepTime);
    return () => window.clearInterval(id);
  }, [value]);
  return <span className="tabular-nums">{display}</span>;
}

const metricConfig = [
  {
    key: "documents",
    label: "Documents",
    get: (b: UserBrain) => b.document_count,
    icon: FileText,
    iconClass: "bg-primary/15 text-primary",
  },
  {
    key: "entities",
    label: "Total entities",
    get: (b: UserBrain) => b.total_nodes,
    icon: Boxes,
    iconClass: "bg-[hsl(180_55%_40%/0.15)] text-[hsl(180_55%_45%)]",
  },
  {
    key: "relationships",
    label: "Relationships",
    get: (b: UserBrain) => b.total_edges,
    icon: GitFork,
    iconClass: "bg-primary/10 text-primary/90",
  },
  {
    key: "communities",
    label: "Communities",
    get: (b: UserBrain) => b.community_count,
    icon: Users,
    iconClass: "bg-muted text-muted-foreground",
  },
] as const;

export function BrainMetrics({ brain, isLoading }: BrainMetricsProps) {
  if (isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <Card key={i} variant="accent">
            <CardContent className="flex gap-3 p-4">
              <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-7 w-12" />
              </div>
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

  return (
    <TooltipProvider delayDuration={200}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {metricConfig.map(({ key, label, get, icon: Icon, iconClass }, index) => {
          const value = get(brain);
          return (
            <motion.div
              key={key}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05, duration: 0.25 }}
            >
              <Tooltip>
                <TooltipTrigger asChild>
                  <Card
                    variant="accent"
                    className={cn(
                      "cursor-default transition-shadow duration-200",
                      "hover:shadow-md hover:shadow-primary/5"
                    )}
                  >
                    <CardContent className="flex gap-3 p-4">
                      <div
                        className={cn(
                          "flex h-10 w-10 shrink-0 items-center justify-center rounded-full",
                          iconClass
                        )}
                      >
                        <Icon className="h-4 w-4" aria-hidden />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                          {label}
                        </p>
                        <p className="font-heading mt-1 text-2xl font-bold text-foreground">
                          <CountUp value={value} />
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  <span className="font-medium">{label}:</span> {value}
                </TooltipContent>
              </Tooltip>
            </motion.div>
          );
        })}
        {brain.last_updated && (
          <p className="col-span-full text-xs text-muted-foreground">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="cursor-default border-b border-dotted border-muted-foreground/40">
                  Updated {formatRelativeTime(brain.last_updated)}
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {new Date(brain.last_updated).toLocaleString()}
              </TooltipContent>
            </Tooltip>
          </p>
        )}
      </div>
    </TooltipProvider>
  );
}
