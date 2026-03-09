"use client";

import { useCallback, useState } from "react";
import * as api from "@/lib/api";

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

  const reset = useCallback(() => {
    setState("idle");
    setProgress(null);
    setJobId(null);
    setPipelineJobId(null);
    setDocumentName(null);
    setGraph(null);
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
            completed: total,
            total,
            message: "Building relationships from entities…",
          });

          const graphPoll = async (): Promise<void> => {
            if (Date.now() - start > TIMEOUT_MS) {
              setState("error");
              setError("Extraction timed out.");
              setProgress(null);
              return;
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
              setTimeout(pollPipeline, POLL_INTERVAL_MS);
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
            };

            if (status.status === "running") {
              let pipelineState: ProcessingState = "detecting_communities";
              if (status.step === "summarizing") pipelineState = "summarizing";
              if (status.step === "embedding") pipelineState = "embedding";
              setState(pipelineState);
              setProgress({
                completed: status.step_index - 1,
                total: status.total_steps,
                message: status.message,
              });
              setTimeout(pollPipeline, POLL_INTERVAL_MS);
              return;
            }
            if (status.status === "failed") {
              setState("error");
              setError(status.error || "Graph pipeline failed.");
              setProgress(null);
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
            // Refresh graph from Neo4j so it includes community assignments
            if (graph.filename) {
              void (async () => {
                try {
                  const enriched = await api.getGraphFromNeo4j(graph.filename, token);
                  setGraph(enriched);
                } catch {
                  // fall back to extracted graph
                }
              })();
            }
            resolve();
          } catch (err) {
            setState("error");
            setError(
              err instanceof Error
                ? err.message
                : "Failed to fetch pipeline status."
            );
            setProgress(null);
            reject(
              err instanceof Error
                ? err
                : new Error("Failed to fetch pipeline status.")
            );
          }
        };
        void pollPipeline();
      });
    } catch (err) {
      if (!(err instanceof Error)) {
        throw err;
      }
      // State and error message have already been set above where appropriate.
      if (!error) {
        setError(err.message);
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
