"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import type { DocumentGraph, CommunityInfo } from "@/lib/api";

interface DocumentGraphViewProps {
  graph: DocumentGraph | null;
  communities?: CommunityInfo[] | null;
}

interface ForceGraphNode {
  id: string;
  label: string;
  type: string;
  communityId?: string;
}

interface ForceGraphLink {
  source: string;
  target: string;
  relation_type?: string;
}

function communityColor(index: number, total: number): string {
  const hue = (index * 360) / Math.max(total, 1);
  return `hsl(${hue % 360}, 65%, 50%)`;
}

export function DocumentGraphView({ graph, communities }: DocumentGraphViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ w: 600, h: 320 });
  const [GraphComponent, setGraphComponent] = useState<React.ComponentType<any> | null>(null);

  useEffect(() => {
    import("react-force-graph-2d").then((mod) => {
      setGraphComponent(() => mod.default);
    });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0]?.contentRect ?? { width: 600, height: 320 };
      setDimensions({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const communityColors = useMemo(() => {
    const colors: Record<string, string> = {};
    (communities ?? []).forEach((c, idx) => {
      colors[c.community_id] = communityColor(idx, communities?.length ?? 1);
    });
    return colors;
  }, [communities]);

  const graphData = useMemo(() => {
    if (!graph) return { nodes: [], links: [] as ForceGraphLink[] };
    const nodes: ForceGraphNode[] = graph.nodes.map((n) => ({
      id: n.id,
      label: n.label,
      type: n.type,
      communityId: (n.properties?.community_id as string) || undefined,
    }));
    const links: ForceGraphLink[] = graph.edges.map((e) => ({
      source: e.source,
      target: e.target,
      relation_type: e.relation_type,
    }));
    return { nodes, links };
  }, [graph]);

  if (!GraphComponent) {
    return (
      <div
        ref={containerRef}
        className="h-[320px] w-full rounded-md bg-muted/30 flex items-center justify-center"
      >
        <span className="text-muted-foreground text-sm">Loading document graph…</span>
      </div>
    );
  }

  if (!graph || !graphData.nodes.length) {
    return (
      <div
        ref={containerRef}
        className="h-[320px] w-full rounded-md bg-muted/30 flex items-center justify-center"
      >
        <span className="text-muted-foreground text-sm">
          No document graph loaded. Select a document or upload one.
        </span>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative h-[320px] w-full rounded-md bg-muted/30 border border-border/60"
    >
      <GraphComponent
        graphData={graphData}
        width={dimensions.w}
        height={dimensions.h}
        nodeLabel={(n: ForceGraphNode) => `${n.label} (${n.type})`}
        nodeColor={(n: ForceGraphNode) =>
          (n.communityId && communityColors[n.communityId]) || "hsl(0,0%,65%)"
        }
        nodeVal={(n: ForceGraphNode) => 3 + (n.communityId ? 2 : 0)}
        linkColor="rgba(200,170,100,0.25)"
        linkWidth={1}
      />
      <div className="absolute bottom-2 left-2 rounded-md border border-border/50 bg-card/95 px-2.5 py-1.5 text-[11px] text-muted-foreground shadow-sm backdrop-blur-sm">
        <div className="font-medium text-foreground/90">
          {graph.filename} · {graph.entity_count} entities · {graph.relationship_count} relationships
        </div>
      </div>
    </div>
  );
}

