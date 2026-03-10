"use client";

import { useCallback, useState } from "react";
import * as api from "@/lib/api";

declare const process: {
  env: Record<string, string | undefined>;
};

const POLL_INTERVAL_MS = 2000;
const TIMEOUT_MS = 600_000; // 10 min

export type ProcessingState =
  | "idle"
  | "uploading"
  | "extracting_entities"
  | "extracting_relationships"
  | "saving_graph"
  | "detecting_communities"
  | "summarizing"
  | "embedding"
  | "preview"
  | "done"
  | "error";

export interface ProcessingProgress {
  completed: number;
  total: number;
  message: string;
}

type SaveGraphToNeo4jResponse = {
  ok: boolean;
  document_name: string;
  pipeline_job_id: string;
  message: string;
};

export function useUpload(token: string | null) {
  const [state, setState] = useState<ProcessingState>("idle");
  const [progress, setProgress] = useState<ProcessingProgress | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [graph, setGraph] = useState<api.DocumentGraph | null>(null);
  const [pipelineJobId, setPipelineJobId] = useState<string | null>(null);
  const [documentName, setDocumentName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const reset = useCallback((options?: { keepGraph?: boolean }) => {
    setState("idle");
    setProgress(null);
    setJobId(null);
    setPipelineJobId(null);
    setDocumentName(null);
    if (!options?.keepGraph) {
      setGraph(null);
    }
    setError(null);
    setSelectedFile(null);
  }, []);

  const uploadAndProcess = useCallback(
    async (file: File) => {
      if (!token) return;
      setSelectedFile(file);
      setError(null);
      setState("uploading");
      setProgress({ completed: 0, total: 1, message: "Uploading…" });

      try {
        await api.uploadPdf(file, token);
        setProgress({ completed: 1, total: 1, message: "Starting extraction…" });

        const { job_id } = await api.startEntityExtraction(token);
        setJobId(job_id);
        setState("extracting_entities");

        const start = Date.now();
        const poll = async (): Promise<void> => {
          if (Date.now() - start > TIMEOUT_MS) {
            setState("error");
            setError("Extraction timed out.");
            setProgress(null);
            return;
          }
          const status = await api.getExtractionStatus(job_id, token);
          const total = Math.max(status.total_chunks, 1);
          const completed = status.completed_chunks;

          if (status.status === "running" || status.status === "pending") {
            setProgress({
              completed,
              total,
              message: `Extracting entities: ${completed}/${total} chunks`,
            });
            setTimeout(poll, POLL_INTERVAL_MS);
            return;
          }
          if (status.status === "failed") {
            setState("error");
            setError(status.error || "Extraction failed.");
            setProgress(null);
            return;
          }

          setState("extracting_relationships");
          setProgress({
            completed: 0,
            total,
            message: "Extracting relationships…",
          });

          const graphPoll = async (): Promise<void> => {
            if (Date.now() - start > TIMEOUT_MS) {
              setState("error");
              setError("Extraction timed out.");
              setProgress(null);
              return;
            }
            try {
              const relRes = await fetch(
                `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/entities/extract/relationships/status/${encodeURIComponent(
                  `${job_id}_rel`
                )}`,
                {
                  headers: {
                    "Content-Type": "application/json",
                    Authorization: `Bearer ${token}`,
                  },
                }
              );
              if (relRes.ok) {
                const relStatus = (await relRes.json()) as {
                  status: "running" | "done" | "failed" | "pending" | "completed";
                  total_chunks: number;
                  completed_chunks: number;
                };
                if (
                  relStatus.status === "running" ||
                  relStatus.status === "pending"
                ) {
                  const relTotal = Math.max(relStatus.total_chunks, 1);
                  const relCompleted = relStatus.completed_chunks;
                  setProgress({
                    completed: relCompleted,
                    total: relTotal,
                    message: `Extracting relationships: ${relCompleted}/${relTotal} chunks`,
                  });
                }
              }
            } catch {
              // Best-effort; still continue polling for graph readiness
            }

            const graphData = await api.getExtractionGraph(job_id, token);
            if (graphData) {
              setGraph(graphData);
              setDocumentName(graphData.filename);
              // Stop the automatic save + pipeline here; the user must now
              // confirm by clicking "Add to Brain" to persist the graph and
              // run the full GraphRAG pipeline.
              setState("preview");
              setProgress({
                completed: 1,
                total: 1,
                message: "Preview ready. Review the graph, then Add to Brain to save.",
              });
              return;
            }
            setTimeout(graphPoll, POLL_INTERVAL_MS);
          };
          graphPoll();
        };
        poll();
      } catch (e) {
        setState("error");
        setError(e instanceof api.ApiError ? e.message : "Upload failed.");
        setProgress(null);
      }
    },
    [token]
  );

  const addToBrain = useCallback(async (): Promise<void> => {
    if (!token || !jobId || !graph) {
      throw new Error("Nothing to add to brain yet.");
    }

    // Track whether a more specific error message has already been set
    // inside the pipeline polling logic so we don't overwrite it in the
    // outer catch block below.
    let hasExplicitPipelineError = false;

    try {
      setState("saving_graph");
      setProgress({
        completed: 0,
        total: 1,
        message: "Saving graph to knowledge base…",
      });
      const rawSaveResult = await api.saveGraphToNeo4j(jobId, token);
      const { pipeline_job_id: pipelineId } = rawSaveResult as SaveGraphToNeo4jResponse;
      if (!pipelineId) {
        throw new Error("Pipeline job id missing from save response.");
      }
      setPipelineJobId(pipelineId);
      setState("detecting_communities");
      setProgress({
        completed: 0,
        total: 3,
        message: "Starting brain pipeline…",
      });
      const pipelineStart = Date.now();

      await new Promise<void>((resolve, reject) => {
        const pollPipeline = async (): Promise<void> => {
          if (Date.now() - pipelineStart > TIMEOUT_MS) {
            setState("error");
            setError("Graph pipeline timed out.");
            setProgress(null);
            hasExplicitPipelineError = true;
            reject(new Error("Graph pipeline timed out."));
            return;
          }
          try {
            const res = await fetch(
              `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/graph/pipeline/status/${encodeURIComponent(
                pipelineId
              )}`,
              {
                headers: {
                  "Content-Type": "application/json",
                  Authorization: `Bearer ${token}`,
                },
              }
            );

            // The background pipeline may not have written status yet; treat 404 as transient.
            if (res.status === 404) {
              setTimeout(pollPipeline, 500);
              return;
            }

            if (!res.ok) {
              throw new Error("Failed to fetch pipeline status.");
            }
            const status = (await res.json()) as {
              status: "running" | "done" | "failed";
              step: string;
              step_index: number;
              total_steps: number;
              message: string;
              error?: string;
              community_progress?: { completed: number; total: number };
            };

            if (status.status === "running") {
              let pipelineState: ProcessingState = "detecting_communities";
              if (status.step === "summarizing") pipelineState = "summarizing";
              if (status.step === "embedding") pipelineState = "embedding";
              setState(pipelineState);
              const summaryProgress = status.community_progress;
              const completed =
                status.step === "summarizing" && summaryProgress
                  ? summaryProgress.completed
                  : Math.max(0, status.step_index - 1);
              const total =
                status.step === "summarizing" && summaryProgress
                  ? Math.max(1, summaryProgress.total)
                  : status.total_steps;
              setProgress({
                completed,
                total,
                message: status.message,
              });
              const nextPollMs =
                status.step === "summarizing" || status.step === "embedding"
                  ? POLL_INTERVAL_MS
                  : 1000;
              setTimeout(pollPipeline, nextPollMs);
              return;
            }
            if (status.status === "failed") {
              setState("error");
              setError(status.error || "Graph pipeline failed.");
              setProgress(null);
              hasExplicitPipelineError = true;
              reject(new Error(status.error || "Graph pipeline failed."));
              return;
            }

            // done
            setState("done");
            setProgress({
              completed: status.total_steps,
              total: status.total_steps,
              message: "Graph pipeline complete. Brain updated.",
            });
            // Refresh graph from Neo4j so it includes community assignments.
            // This is awaited before resolving so callers (e.g. PdfUpload) do not
            // call reset() and clear state before the enriched graph is applied.
            if (graph.filename) {
              try {
                const enriched = await api.getGraphFromNeo4j(graph.filename, token);
                setGraph(enriched);
              } catch {
                // fall back to extracted graph
              }
            }
            resolve();
          } catch (err) {
            const message =
              err instanceof Error ? err.message : "Failed to fetch pipeline status.";
            setState("error");
            setError(message);
            setProgress(null);
            hasExplicitPipelineError = true;
            reject(
              err instanceof Error
                ? err
                : new Error(message)
            );
          }
        };
        void pollPipeline();
      });
    } catch (err) {
      if (!(err instanceof Error)) {
        throw err;
      }
      // If the polling logic already set a specific error message/state, keep it.
      // Otherwise, ensure we surface this error to the user here.
      if (!hasExplicitPipelineError) {
        setState("error");
        setError(err.message);
        setProgress(null);
      }
      throw err;
    }
  }, [token, jobId, graph]);

  return {
    state,
    progress,
    jobId,
    graph,
    pipelineJobId,
    documentName,
    error,
    selectedFile,
    uploadAndProcess,
    addToBrain,
    reset,
    setError,
  };
}
