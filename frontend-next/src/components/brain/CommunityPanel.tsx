"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { CommunityInfo } from "@/lib/api";

interface CommunityPanelProps {
  community: CommunityInfo | null;
  open: boolean;
  onClose: () => void;
}

export function CommunityPanel({ community, open, onClose }: CommunityPanelProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    if (open) window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-black/20"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.div
            className="fixed right-0 top-0 z-50 h-full w-full max-w-md border-l bg-background shadow-lg"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
          >
            <div className="flex h-full flex-col p-4">
              <div className="flex items-center justify-between border-b pb-3">
                <h2 className="text-lg font-semibold">Community</h2>
                <Button variant="ghost" size="sm" onClick={onClose}>
                  Close
                </Button>
              </div>
              <div className="flex-1 overflow-y-auto pt-3">
                {community ? (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">
                        {community.community_id}
                      </CardTitle>
                      <p className="text-sm text-muted-foreground">
                        {community.node_count} entities
                      </p>
                    </CardHeader>
                    <CardContent className="space-y-4 text-sm">
                      {community.top_entities?.length > 0 && (
                        <div>
                          <p className="font-medium text-muted-foreground">
                            Top entities
                          </p>
                          <ul className="mt-1 list-inside list-disc space-y-0.5">
                            {community.top_entities.map((e, i) => (
                              <li key={i}>{e}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {community.keywords?.length > 0 && (
                        <div>
                          <p className="font-medium text-muted-foreground">
                            Keywords
                          </p>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {community.keywords.map((k, i) => (
                              <span
                                key={i}
                                className="rounded bg-muted px-2 py-0.5 text-xs"
                              >
                                {k}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {community.document_sources?.length > 0 && (
                        <div>
                          <p className="font-medium text-muted-foreground">
                            Document sources
                          </p>
                          <ul className="mt-1 list-inside list-disc space-y-0.5 text-muted-foreground">
                            {community.document_sources.map((d, i) => (
                              <li key={i}>{d}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ) : (
                  <p className="text-muted-foreground">
                    Select a node on the graph to view its community.
                  </p>
                )}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
