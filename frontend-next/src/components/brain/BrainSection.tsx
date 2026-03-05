"use client";

import { useMemo, useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { BrainMetrics } from "./BrainMetrics";
import { BrainGraph, type GraphDataInput } from "./BrainGraph";
import { CommunityPanel } from "./CommunityPanel";
import { useBrain } from "@/hooks/useBrain";
import * as api from "@/lib/api";
import type { CommunityInfo } from "@/lib/api";

interface BrainSectionProps {
  token: string;
}

export function BrainSection({ token }: BrainSectionProps) {
  const { brain, isLoading, refresh, remove, mutate } = useBrain(token);
  const [highlightedCommunityId, setHighlightedCommunityId] = useState<string | null>(null);
  const [panelCommunity, setPanelCommunity] = useState<CommunityInfo | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [graphData, setGraphData] = useState<{ documents: api.DocumentListItem[]; graphs: api.DocumentGraph[] } | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

  const loadGraphData = async () => {
    setGraphLoading(true);
    try {
      const documents = await api.listNeo4jDocuments(token);
      const graphs: api.DocumentGraph[] = [];
      for (const doc of documents) {
        try {
          const g = await api.getGraphFromNeo4j(doc.document_name, token);
          graphs.push(g);
        } catch {
          // skip failed doc
        }
      }
      setGraphData({ documents, graphs });
    } catch {
      setGraphData(null);
    } finally {
      setGraphLoading(false);
    }
  };

  const graphInput: GraphDataInput | null = useMemo(() => {
    if (!brain || !graphData) return null;
    return {
      documents: graphData.documents,
      graphs: graphData.graphs,
      communities: brain.communities,
    };
  }, [brain, graphData]);

  const handleNodeClick = (_node: unknown, community: CommunityInfo | null) => {
    setPanelCommunity(community);
    setHighlightedCommunityId(community?.community_id ?? null);
    setPanelOpen(true);
  };

  const handleRefresh = async () => {
    await refresh();
    await loadGraphData();
  };

  return (
    <Card variant="accent">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="font-heading">Knowledge Brain</CardTitle>
          <CardDescription>
            Your merged knowledge graph and communities across all documents.
          </CardDescription>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadGraphData}
            disabled={graphLoading || !brain}
          >
            {graphLoading ? "Loading…" : "Load graph"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isLoading || !brain}
          >
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <BrainMetrics brain={brain} isLoading={isLoading} />
        {brain && (
          <div className="space-y-2">
            <h3 className="text-sm font-medium">Graph</h3>
            <BrainGraph
              input={graphInput}
              highlightedCommunityId={highlightedCommunityId}
              onNodeClick={handleNodeClick}
            />
          </div>
        )}
        <details className="text-sm text-muted-foreground">
          <summary className="cursor-pointer hover:text-foreground">
            Clear brain — start from scratch
          </summary>
          <div className="mt-2">
            <Button
              variant="destructive"
              size="sm"
              onClick={remove}
              disabled={!brain || isLoading}
            >
              Delete brain and all documents
            </Button>
          </div>
        </details>
      </CardContent>
      <CommunityPanel
        community={panelCommunity}
        open={panelOpen}
        onClose={() => {
          setPanelOpen(false);
          setHighlightedCommunityId(null);
        }}
      />
    </Card>
  );
}
