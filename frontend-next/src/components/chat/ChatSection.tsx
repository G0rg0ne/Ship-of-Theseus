"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import type { DocumentListItem } from "@/lib/api";

function MessageIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function SendIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  );
}

interface ChatSectionProps {
  documents?: DocumentListItem[];
}

/**
 * Chat section UI. User can type and send (no backend yet).
 * Document context badges show which docs are in the knowledge base.
 */
export function ChatSection({ documents = [] }: ChatSectionProps) {
  const [inputValue, setInputValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Minimal auto-grow for textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [inputValue]);

  const handleSend = () => {
    // No-op until bot is implemented
    setInputValue("");
  };

  return (
    <section className="flex flex-1 min-h-0 flex-col px-4 py-6">
      <header className="shrink-0 mb-3">
        <h2 className="font-heading text-lg font-semibold tracking-tight text-foreground">
          Ask your brain
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Chat with your uploaded documents.
        </p>
      </header>

      {documents.length > 0 && (
        <div className="shrink-0 flex flex-wrap gap-1.5 mb-3">
          {documents.slice(0, 5).map((doc) => (
            <span
              key={doc.document_name}
              className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
              title={doc.document_name}
            >
              {doc.document_name.length > 18
                ? `${doc.document_name.slice(0, 15)}…`
                : doc.document_name}
            </span>
          ))}
          {documents.length > 5 && (
            <span className="text-xs text-muted-foreground">
              +{documents.length - 5} more
            </span>
          )}
        </div>
      )}

      {/* Messages area – scrollable */}
      <div className="flex-1 min-h-0 rounded-lg border border-border bg-card/50 overflow-auto flex flex-col">
        <div className="flex flex-1 min-h-[10rem] flex-col items-center justify-center p-4 text-center">
          <MessageIcon className="h-10 w-10 text-muted-foreground/60 mb-3" />
          <p className="text-sm text-muted-foreground">
            No messages yet — ask anything about your documents.
          </p>
        </div>
      </div>

      {/* Input footer – pinned to bottom */}
      <div className="shrink-0 pt-3 flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          placeholder="Type a message…"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={1}
          className="flex-1 min-h-[40px] max-h-[120px] resize-none rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Chat message input"
        />
        <Button
          type="button"
          size="icon"
          className="shrink-0 h-[40px] w-[40px]"
          onClick={handleSend}
          aria-label="Send message"
        >
          <SendIcon className="h-4 w-4" />
        </Button>
      </div>
    </section>
  );
}
