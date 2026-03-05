"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphNode, GraphEdge, DocumentGraph, CommunityInfo } from "@/lib/api";

export interface GraphDataInput {
  documents: { document_name: string }[];
  graphs: DocumentGraph[];
  communities: CommunityInfo[];
}

interface ForceGraphNode extends GraphNode {
  mergedId?: string;
  communityId?: string;
  documentName?: string;
}

interface ForceGraphLink {
  source: string;
  target: string;
  relation_type?: string;
}

// HSL palette for communities
function communityColor(index: number, total: number): string {
  const hue = (index * 360) / Math.max(total, 1) % 360;
  return `hsl(${hue}, 65%, 50%)`;
}

function buildGraphData(input: GraphDataInput): {
  nodes: ForceGraphNode[];
  links: ForceGraphLink[];
  communityColors: Record<string, string>;
} {
  const nodeMap = new Map<string, ForceGraphNode>();
  const links: ForceGraphLink[] = [];
  const communityColors: Record<string, string> = {};

  input.communities.forEach((c, i) => {
    communityColors[c.community_id] = communityColor(i, input.communities.length);
  });

  input.graphs.forEach((g) => {
    const docName = g.filename;
    g.nodes.forEach((n) => {
      const mergedId = `${docName}::${n.id}`;
      const communityId = (n.properties?.community_id as string) || undefined;
      if (!nodeMap.has(mergedId)) {
        nodeMap.set(mergedId, {
          ...n,
          id: mergedId,
          mergedId,
          communityId,
          documentName: docName,
        });
      }
    });
    g.edges.forEach((e) => {
      links.push({
        source: `${docName}::${e.source}`,
        target: `${docName}::${e.target}`,
        relation_type: e.relation_type,
      });
    });
  });

  return {
    nodes: Array.from(nodeMap.values()),
    links,
    communityColors,
  };
}

interface BrainGraphProps {
  input: GraphDataInput | null;
  onNodeClick?: (node: ForceGraphNode, community: CommunityInfo | null) => void;
  highlightedCommunityId: string | null;
}

export function BrainGraph({
  input,
  onNodeClick,
  highlightedCommunityId,
}: BrainGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ w: 600, h: 400 });
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
      const { width, height } = entries[0]?.contentRect ?? { width: 600, height: 400 };
      setDimensions({ w: width, h: height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { nodes, links, communityColors } = useMemo(() => {
    if (!input?.graphs?.length) return { nodes: [], links: [], communityColors: {} as Record<string, string> };
    return buildGraphData(input);
  }, [input]);

  const graphData = useMemo(
    () => ({
      nodes: nodes.map((n) => ({ ...n, id: n.id })),
      links,
    }),
    [nodes, links]
  );

  const nodeColor = useCallback(
    (node: ForceGraphNode) => {
      const cid = node.communityId ?? "";
      if (highlightedCommunityId && cid !== highlightedCommunityId) {
        return "rgba(128,128,128,0.2)";
      }
      return communityColors[cid] || "hsl(0,0%,60%)";
    },
    [communityColors, highlightedCommunityId]
  );

  const communityByNodeId = useMemo(() => {
    const map = new Map<string, CommunityInfo>();
    input?.communities?.forEach((c) => {
      // We don't have node_ids in CommunityInfo from API; match by community_id on node
      map.set(c.community_id, c);
    });
    return map;
  }, [input?.communities]);

  const handleNodeClick = useCallback(
    (node: { id: string; communityId?: string }) => {
      const fullNode = nodes.find((n) => n.id === node.id);
      const community = fullNode?.communityId
        ? input?.communities?.find((c) => c.community_id === fullNode.communityId) ?? null
        : null;
      onNodeClick?.(fullNode as ForceGraphNode, community ?? null);
    },
    [nodes, input?.communities, onNodeClick]
  );

  if (!GraphComponent) {
    return (
      <div ref={containerRef} className="h-[400px] w-full rounded-md bg-muted/30 flex items-center justify-center">
        <span className="text-muted-foreground">Loading graph…</span>
      </div>
    );
  }

  if (!nodes.length) {
    return (
      <div ref={containerRef} className="h-[400px] w-full rounded-md bg-muted/30 flex items-center justify-center">
        <span className="text-muted-foreground">No graph data. Add documents to the knowledge base.</span>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative h-[400px] w-full rounded-md bg-muted/30">
      <GraphComponent
        graphData={graphData}
        width={dimensions.w}
        height={dimensions.h}
        nodeLabel={(n: ForceGraphNode) =>
          `${n.label} (${n.type})${n.documentName ? ` · ${n.documentName}` : ""}`
        }
        nodeColor={nodeColor}
        nodeVal={(n: ForceGraphNode) => 3 + (n.communityId ? 2 : 0)}
        linkColor="rgba(200,170,100,0.25)"
        linkWidth={1}
        onNodeClick={handleNodeClick}
      />
      <div className="absolute bottom-2 left-2 rounded-md border border-border/50 bg-card/95 px-2.5 py-1.5 text-xs text-muted-foreground shadow-sm backdrop-blur-sm">
        <span className="font-medium text-foreground/90">Entity types:</span> Person · Org · Location · Key term
      </div>
    </div>
  );
}
