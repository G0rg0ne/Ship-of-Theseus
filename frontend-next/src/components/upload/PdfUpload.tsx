"use client";

import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ProcessingSteps } from "./ProcessingSteps";
import { useUpload, type ProcessingState } from "@/hooks/useUpload";
import * as api from "@/lib/api";

const MAX_SIZE_MB = 10;
const MAX_BYTES = MAX_SIZE_MB * 1024 * 1024;

interface PdfUploadProps {
  token: string;
  onSaveComplete?: () => void;
}

export function PdfUpload({ token, onSaveComplete }: PdfUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [saveLoading, setSaveLoading] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const {
    state,
    progress,
    jobId,
    graph,
    error,
    selectedFile,
    uploadAndProcess,
    reset,
    setError,
  } = useUpload(token);

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      if (file.size > MAX_BYTES) {
        setError(`File must be under ${MAX_SIZE_MB}MB`);
        return;
      }
      if (file.type !== "application/pdf") {
        setError("Please select a PDF file.");
        return;
      }
      uploadAndProcess(file);
    },
    [uploadAndProcess, setError]
  );

  const handleProcessClick = () => {
    inputRef.current?.click();
  };

  const handleAddToKnowledgeBase = async () => {
    if (!jobId || !token) return;
    setSaveError(null);
    setSaveLoading(true);
    try {
      await api.saveGraphToNeo4j(jobId, token);
      onSaveComplete?.();
    } catch (e) {
      setSaveError(e instanceof api.ApiError ? e.message : "Failed to save.");
    } finally {
      setSaveLoading(false);
    }
  };

  const handleClearDocument = async () => {
    try {
      await api.clearCurrentDocument(token);
      reset();
      setSaveError(null);
    } catch {
      // ignore
    }
  };

  const isProcessing: boolean =
    state === "uploading" ||
    state === "extracting_entities" ||
    state === "extracting_relationships";

  return (
    <Card variant="accent">
      <CardHeader>
        <CardTitle className="font-heading">PDF Document</CardTitle>
        <CardDescription>
          Upload a PDF to extract entities and relationships into your knowledge graph.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          className="hidden"
        />

        {state === "idle" && (
          <Button onClick={handleProcessClick} className="w-full">
            Choose PDF and process
          </Button>
        )}

        {selectedFile && (
          <p className="text-sm text-muted-foreground">
            Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
          </p>
        )}

        {isProcessing && (
          <div className="rounded-md border bg-muted/50 p-4">
            <ProcessingSteps
              progress={progress}
              entityCount={state === "done" ? graph?.entity_count : undefined}
              relationshipCount={
                state === "done" ? graph?.relationship_count : undefined
              }
            />
          </div>
        )}

        {state === "done" && graph && (
          <div className="space-y-2">
            <ProcessingSteps
              progress={null}
              entityCount={graph.entity_count}
              relationshipCount={graph.relationship_count}
            />
            {saveError && (
              <p className="text-sm text-destructive">{saveError}</p>
            )}
            <div className="flex gap-2">
              <Button
                onClick={handleAddToKnowledgeBase}
                disabled={saveLoading}
              >
                {saveLoading ? "Saving…" : "Add to Knowledge Base"}
              </Button>
              <Button variant="outline" onClick={() => reset()}>
                Upload another
              </Button>
            </div>
          </div>
        )}

        {state === "error" && error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        {state === "error" && (
          <Button variant="outline" onClick={() => reset()}>
            Try again
          </Button>
        )}

        {(state === "idle" || state === "done" || state === "error") && (
          <details className="text-sm text-muted-foreground">
            <summary className="cursor-pointer hover:text-foreground">
              Clear document and start over
            </summary>
            <div className="mt-2 flex items-center gap-2">
              <Button variant="destructive" size="sm" onClick={handleClearDocument}>
                Clear document
              </Button>
            </div>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
