"use client";

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  forwardRef,
  useRef,
  useState,
} from "react";
import { FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ProcessingSteps } from "./ProcessingSteps";
import { useUpload, type ProcessingState } from "@/hooks/useUpload";
import * as api from "@/lib/api";

const MAX_SIZE_MB = 10;
const MAX_BYTES = MAX_SIZE_MB * 1024 * 1024;

export interface PdfUploadHandle {
  openFilePicker: () => void;
}

interface PdfUploadProps {
  token: string;
  onSaveComplete?: () => void;
  /** Icon-only control for collapsed sidebar */
  compact?: boolean;
  /** Called when pipeline starts while compact — parent should expand the sidebar */
  onExpandForUpload?: () => void;
}

export const PdfUpload = forwardRef<PdfUploadHandle, PdfUploadProps>(
  function PdfUpload({ token, onSaveComplete, compact = false, onExpandForUpload }, ref) {
    const inputRef = useRef<HTMLInputElement>(null);
    const didExpandForPipeline = useRef(false);
    const [saveLoading, setSaveLoading] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const {
      state,
      progress,
      graph,
      error,
      selectedFile,
      uploadAndProcess,
      addToBrain,
      reset,
      setError,
    } = useUpload(token);

    useImperativeHandle(ref, () => ({
      openFilePicker: () => inputRef.current?.click(),
    }));

    useEffect(() => {
      if (!compact) {
        didExpandForPipeline.current = false;
        return;
      }
      if (state === "idle") {
        didExpandForPipeline.current = false;
        return;
      }
      if (!didExpandForPipeline.current && onExpandForUpload) {
        didExpandForPipeline.current = true;
        onExpandForUpload();
      }
    }, [compact, state, onExpandForUpload]);

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

    const handleClearDocument = async () => {
      try {
        await api.clearCurrentDocument(token);
        reset();
        setSaveError(null);
      } catch {
        // ignore
      }
    };

    const handleAddToBrain = async () => {
      try {
        setSaveError(null);
        setSaveLoading(true);
        await addToBrain();
        if (onSaveComplete) {
          await Promise.resolve(onSaveComplete());
        }
        reset({ keepGraph: true });
      } catch (err) {
        setSaveError(
          err instanceof Error
            ? err.message
            : "Failed to refresh brain. Please try again."
        );
      } finally {
        setSaveLoading(false);
      }
    };

    const isProcessing: boolean =
      state === "uploading" ||
      state === "extracting_entities" ||
      state === "extracting_relationships" ||
      state === "saving_graph" ||
      state === "detecting_communities" ||
      state === "summarizing" ||
      state === "embedding";

    /** Collapsed sidebar: icon only when idle; full card while pipeline runs */
    const useCompactChrome = compact && state === "idle";

    const sharedInput = (
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,application/pdf"
        onChange={handleFileChange}
        className="hidden"
      />
    );

    if (useCompactChrome) {
      return (
        <div className="flex flex-col items-center gap-1">
          {sharedInput}
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-10 w-10 shrink-0 border-primary/20 bg-primary/5 hover:bg-primary/10"
            onClick={handleProcessClick}
            aria-label="Choose PDF and process"
            title="Upload PDF"
          >
            <FileUp className="h-4 w-4 text-primary" />
          </Button>
        </div>
      );
    }

    return (
      <Card variant="accent" className="min-w-0">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-heading">
            <FileUp className="h-4 w-4 text-primary" aria-hidden />
            PDF Document
          </CardTitle>
          <CardDescription>
            Upload a PDF to extract entities and relationships into your knowledge graph.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {sharedInput}

          {state === "idle" && (
            <Button onClick={handleProcessClick} className="w-full">
              Choose PDF and process
            </Button>
          )}

          {selectedFile && (
            <p className="text-sm text-muted-foreground truncate" title={selectedFile.name}>
              Selected: {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
            </p>
          )}

          {isProcessing && (
            <div className="rounded-md border bg-muted/50 p-4">
              <ProcessingSteps
                state={state}
                progress={progress}
                entityCount={state === "done" ? graph?.entity_count : undefined}
                relationshipCount={
                  state === "done" ? graph?.relationship_count : undefined
                }
              />
            </div>
          )}

          {state === "preview" && graph && (
            <div className="space-y-2">
              <ProcessingSteps
                state={state}
                progress={progress}
                entityCount={graph.entity_count}
                relationshipCount={graph.relationship_count}
              />
              {saveError && <p className="text-sm text-destructive">{saveError}</p>}
              <div className="flex flex-col gap-2">
                <Button onClick={handleAddToBrain} disabled={saveLoading} className="w-full">
                  {saveLoading ? "Refreshing brain…" : "Add to Brain"}
                </Button>
                <Button variant="outline" onClick={() => reset()} className="w-full">
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
            <Button variant="outline" onClick={() => reset()} className="w-full">
              Try again
            </Button>
          )}

          {(state === "idle" || state === "done" || state === "error") && (
            <details className="text-sm text-muted-foreground">
              <summary className="cursor-pointer hover:text-foreground">
                Clear document and start over
              </summary>
              <div className="mt-2">
                <Button variant="destructive" size="sm" onClick={handleClearDocument} className="w-full">
                  Clear document
                </Button>
              </div>
            </details>
          )}
        </CardContent>
      </Card>
    );
  }
);

PdfUpload.displayName = "PdfUpload";
