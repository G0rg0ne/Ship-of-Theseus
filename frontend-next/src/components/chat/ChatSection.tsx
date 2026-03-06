"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";

/**
 * Chat section placeholder. User can type in the input; no send or response yet.
 * Chatbot integration will be added later.
 */
export function ChatSection() {
  const [inputValue, setInputValue] = useState("");

  return (
    <section className="flex flex-1 min-h-0 flex-col">
      <h2 className="font-heading text-xl font-semibold tracking-tight text-foreground pl-3 border-l-2 border-primary/70 shrink-0">
        Chat
      </h2>
      <p className="text-sm text-muted-foreground mt-2 mb-4 shrink-0">
        Ask questions about your knowledge graph. Responses will be connected
        here later.
      </p>

      {/* Messages area – scrollable; fills space above the input */}
      <div className="flex-1 min-h-0 rounded-lg border border-border bg-card/50 overflow-auto p-4">
        <div className="flex h-full min-h-[8rem] items-center justify-center text-muted-foreground text-sm">
          No messages yet. Type below to get started.
        </div>
      </div>

      {/* User input – pinned to bottom, no scrolling needed */}
      <div className="shrink-0 pt-4">
        <Input
          type="text"
          placeholder="Type a message…"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          className="w-full"
          aria-label="Chat message input"
        />
      </div>
    </section>
  );
}
