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
  | "done"
  | "error";

export interface ProcessingProgress {
  completed: number;
  total: number;
  message: string;
}

export function useUpload(token: string | null) {
  const [state, setState] = useState<ProcessingState>("idle");
  const [progress, setProgress] = useState<ProcessingProgress | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [graph, setGraph] = useState<api.DocumentGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const reset = useCallback(() => {
    setState("idle");
    setProgress(null);
    setJobId(null);
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
              setState("done");
              setProgress(null);
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

  return {
    state,
    progress,
    jobId,
    graph,
    error,
    selectedFile,
    uploadAndProcess,
    reset,
    setError,
  };
}
