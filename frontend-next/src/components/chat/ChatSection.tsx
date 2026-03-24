"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageSquare, Send, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  ApiError,
  type DocumentListItem,
  type SourceAttribution,
  type UserBrain,
} from "@/lib/api";

const NO_BRAIN_REPLY = "Please upload your document first.";
import { cn } from "@/lib/utils";

const getApiBaseUrl = () =>
  typeof window !== "undefined"
    ? process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const CHAT_SESSION_KEY = "chat_session_id";

const SUGGESTED_PROMPTS = [
  "What are the main themes across my documents?",
  "Summarize the key entities and how they connect.",
  "What communities exist in my knowledge graph?",
];

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: SourceAttribution[];
}

interface ChatSectionProps {
  documents?: DocumentListItem[];
  token?: string | null;
  /** When loaded, used to skip the API when there is no graph/brain yet (mirrors POST /api/query). */
  brain?: UserBrain | null;
  brainLoading?: boolean;
}

/**
 * Chat section: query the GraphRAG brain. Conversation history is kept per session (localStorage).
 */
export function ChatSection({
  documents = [],
  token,
  brain = null,
  brainLoading = false,
}: ChatSectionProps) {
  const [inputValue, setInputValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [inputFocused, setInputFocused] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    let sid = localStorage.getItem(CHAT_SESSION_KEY);
    if (!sid) {
      sid = crypto.randomUUID();
      localStorage.setItem(CHAT_SESSION_KEY, sid);
    }
    setSessionId(sid);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [inputValue]);

  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isLoading) return;
    if (!token) {
      setError("Sign in to chat with your brain.");
      return;
    }
    const hasGraphBrain =
      brainLoading ||
      (brain != null &&
        (brain.document_count > 0 || brain.total_nodes > 0 || brain.community_count > 0));
    if (!hasGraphBrain) {
      setError(null);
      setInputValue("");
      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: NO_BRAIN_REPLY },
      ]);
      return;
    }
    setError(null);
    setInputValue("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsLoading(true);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    try {
      const body = {
        question: text,
        session_id: sessionId ?? undefined,
        stream: true,
      };
      const res = await fetch(getApiBaseUrl() + "/api/query", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + token,
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new ApiError(res.status, typeof data.detail === "string" ? data.detail : "Query failed");
      }
      const reader = res.body?.getReader();
      if (!reader) throw new ApiError(500, "No response body");
      const dec = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;
          try {
            const data = JSON.parse(raw) as {
              content?: string;
              done?: boolean;
              answer?: string;
              mode_used?: string;
              session_id?: string;
              sources?: SourceAttribution[];
            };
            if (data.done) {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  next[next.length - 1] = {
                    role: "assistant",
                    content: data.answer ?? last.content,
                    sources: data.sources,
                  };
                }
                return next;
              });
              if (data.session_id && data.session_id !== sessionId) {
                setSessionId(data.session_id);
                if (typeof window !== "undefined") {
                  localStorage.setItem(CHAT_SESSION_KEY, data.session_id);
                }
              }
            } else if (data.content != null) {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === "assistant") {
                  next[next.length - 1] = { ...last, content: last.content + data.content };
                }
                return next;
              });
            }
          } catch (_) {
            // ignore parse errors for incomplete chunks
          }
        }
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Request failed. Please try again.";
      setError(msg);
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant" && last.content === "") {
          next[next.length - 1] = { role: "assistant", content: msg };
          return next;
        }
        return [...prev, { role: "assistant", content: msg }];
      });
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, token, sessionId, brain, brainLoading]);

  const handleClear = () => {
    setMessages([]);
    if (typeof window !== "undefined") {
      localStorage.removeItem(CHAT_SESSION_KEY);
    }
  };

  const applySuggested = (q: string) => {
    setInputValue(q);
    textareaRef.current?.focus();
  };

  return (
    <section className="flex min-h-0 flex-1 flex-col px-4 py-6">
      <header className="mb-3 shrink-0">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="font-heading text-lg font-semibold tracking-tight text-foreground">
              Ask your brain
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Chat with your uploaded documents.</p>
          </div>
          {messages.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={handleClear}
            >
              Clear
            </Button>
          )}
        </div>
      </header>

      {documents.length > 0 && (
        <div className="mb-3 flex shrink-0 flex-wrap gap-1.5">
          {documents.slice(0, 5).map((doc) => (
            <Badge key={doc.document_name} variant="muted" className="max-w-[140px] truncate font-normal" title={doc.document_name}>
              {doc.document_name.length > 18 ? `${doc.document_name.slice(0, 15)}…` : doc.document_name}
            </Badge>
          ))}
          {documents.length > 5 && (
            <span className="self-center text-xs text-muted-foreground">+{documents.length - 5} more</span>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-border bg-card/60 shadow-inner">
        {messages.length === 0 && !isLoading ? (
          <div className="relative flex min-h-[10rem] flex-1 flex-col items-center justify-center p-6 text-center">
            <div
              className="pointer-events-none absolute inset-0 rounded-xl border border-dashed border-muted-foreground/10 opacity-70 [background-image:radial-gradient(circle_at_top,_hsl(var(--border))_1px,_transparent_0)] [background-size:32px_32px]"
              aria-hidden
            />
            <div className="relative mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <MessageSquare className="h-8 w-8" aria-hidden />
            </div>
            <p className="relative text-sm font-medium text-foreground">No messages yet</p>
            <p className="relative mt-1 max-w-xs text-xs text-muted-foreground">
              Ask anything grounded in your graph. This session stays in your browser until you clear it.
            </p>
            <div className="relative mt-6 w-full max-w-sm space-y-2">
              <p className="flex items-center justify-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <Sparkles className="h-3 w-3" aria-hidden />
                Try asking
              </p>
              <div className="flex flex-col gap-2">
                {SUGGESTED_PROMPTS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => applySuggested(q)}
                    className="rounded-lg border border-border/80 bg-background/60 px-3 py-2 text-left text-xs text-foreground transition-colors hover:border-primary/30 hover:bg-primary/5"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <ScrollArea className="h-full min-h-0 flex-1">
            <div className="flex flex-col gap-3 p-3 pb-4">
              <AnimatePresence initial={false}>
                {messages.map((m, i) => (
                  <motion.div
                    key={i}
                    layout
                    initial={{ opacity: 0, y: 8, x: m.role === "user" ? 8 : -8 }}
                    animate={{ opacity: 1, y: 0, x: 0 }}
                    transition={{ type: "spring", stiffness: 380, damping: 28 }}
                    className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
                  >
                    <div
                      className={cn(
                        "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm",
                        m.role === "user"
                          ? "rounded-br-md bg-primary text-primary-foreground"
                          : "rounded-bl-md bg-muted text-foreground"
                      )}
                    >
                      <div className="mb-1.5 text-[10px] font-medium uppercase tracking-[0.08em] opacity-80">
                        {m.role === "user" ? "You" : "AI"}
                      </div>
                      <p className="whitespace-pre-wrap">
                        {m.role === "assistant" && m.content === "" && isLoading ? (
                          <span className="inline-flex items-center gap-1">
                            <span className="sr-only">Assistant is typing</span>
                            <span className="inline-flex gap-1">
                              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.2s]" />
                              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current [animation-delay:-0.05s]" />
                              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" />
                            </span>
                          </span>
                        ) : (
                          m.content
                        )}
                      </p>
                      {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {m.sources.map((s, j) => (
                            <Badge
                              key={j}
                              variant="outline"
                              className="max-w-full truncate font-normal"
                              title={s.excerpt ?? s.label ?? s.id}
                            >
                              {s.type === "community"
                                ? `Community ${s.id}${s.level ? ` (${s.level})` : ""}`
                                : s.label ?? s.id}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  </motion.div>
                ))}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </div>
          </ScrollArea>
        )}
      </div>

      {error && (
        <p className="mt-1 shrink-0 text-xs text-destructive" role="alert">
          {error}
        </p>
      )}

      <div className="shrink-0 space-y-1.5 pt-3">
        <div
          className={cn(
            "flex items-end gap-2 rounded-xl border bg-background/80 px-3 py-2 shadow-sm transition-[box-shadow,border-color] duration-200",
            inputFocused ? "border-primary/40 shadow-[0_0_0_3px_hsl(var(--primary)/0.12)]" : "border-input"
          )}
        >
          <textarea
            ref={textareaRef}
            placeholder="Ask a question about your brain…"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onFocus={() => setInputFocused(true)}
            onBlur={() => setInputFocused(false)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            disabled={isLoading}
            className="min-h-[40px] max-h-[120px] flex-1 resize-none bg-transparent px-0 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Chat message input"
          />
          <Button
            type="button"
            size="icon"
            className="h-9 w-9 shrink-0 rounded-full"
            onClick={handleSend}
            disabled={isLoading || !inputValue.trim()}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center justify-between px-0.5">
          <p className="text-[10px] text-muted-foreground">Enter to send · Shift+Enter for newline</p>
        </div>
      </div>
    </section>
  );
}
