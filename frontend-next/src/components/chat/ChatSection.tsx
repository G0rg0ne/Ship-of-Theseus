"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  type DocumentListItem,
  type SourceAttribution,
} from "@/lib/api";

const getApiBaseUrl = () =>
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
    : process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const CHAT_SESSION_KEY = "chat_session_id";

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

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: SourceAttribution[];
}

interface ChatSectionProps {
  documents?: DocumentListItem[];
  token?: string | null;
}

/**
 * Chat section: query the GraphRAG brain. Conversation history is kept per session (localStorage).
 */
export function ChatSection({ documents = [], token }: ChatSectionProps) {
  const [inputValue, setInputValue] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
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
    setError(null);
    setInputValue("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setIsLoading(true);
    // Streaming: add placeholder assistant message and append tokens as they arrive
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
        const data = await res.json().catch(() => ({})) as { detail?: string };
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
  }, [inputValue, isLoading, token, sessionId]);

  const handleClear = () => {
    setMessages([]);
    if (typeof window !== "undefined") {
      localStorage.removeItem(CHAT_SESSION_KEY);
    }
  };

  return (
    <section className="flex flex-1 min-h-0 flex-col px-4 py-6">
      <header className="shrink-0 mb-3">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="font-heading text-lg font-semibold tracking-tight text-foreground">
              Ask your brain
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Chat with your uploaded documents.
            </p>
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

      <div className="flex-1 min-h-0 rounded-xl border border-border bg-card/60 overflow-auto flex flex-col scroll-smooth shadow-inner/5">
        {messages.length === 0 && !isLoading ? (
          <div className="relative flex flex-1 min-h-[10rem] flex-col items-center justify-center p-6 text-center">
            <div
              className="pointer-events-none absolute inset-0 rounded-xl border border-dashed border-muted-foreground/10 [background-image:radial-gradient(circle_at_top,_hsl(var(--border))_1px,_transparent_0)] [background-size:32px_32px] opacity-70"
              aria-hidden
            />
            <MessageIcon className="relative h-10 w-10 text-muted-foreground/60 mb-3" />
            <p className="relative text-sm font-medium text-foreground">
              No messages yet — ask anything about your documents.
            </p>
            <p className="relative mt-1 text-xs text-muted-foreground max-w-xs">
              Your conversation stays local to this browser session until you refresh or clear it.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3 p-3 pb-4">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm ${
                    m.role === "user"
                      ? "bg-primary text-primary-foreground rounded-br-md"
                      : "bg-muted text-foreground rounded-bl-md"
                  }`}
                >
                  <div className="mb-1.5 text-[10px] font-medium uppercase tracking-[0.08em] opacity-80">
                    {m.role === "user" ? "You" : "AI"}
                  </div>
                  <p className="whitespace-pre-wrap">
                    {m.role === "assistant" && m.content === "" && isLoading ? (
                      <span className="inline-flex items-center gap-1">
                        <span className="sr-only">Assistant is typing</span>
                        <span className="inline-flex gap-1">
                          <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.2s]" />
                          <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce [animation-delay:-0.05s]" />
                          <span className="h-1.5 w-1.5 rounded-full bg-current animate-bounce" />
                        </span>
                      </span>
                    ) : (
                      m.content
                    )}
                  </p>
                  {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {m.sources.map((s, j) => (
                        <span
                          key={j}
                          className="inline-flex items-center rounded-md bg-background/80 px-2 py-0.5 text-xs font-medium text-muted-foreground"
                          title={s.excerpt ?? s.label ?? s.id}
                        >
                          {s.type === "community"
                            ? `Community ${s.id}${s.level ? ` (${s.level})` : ""}`
                            : s.label ?? s.id}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {error && (
        <p className="shrink-0 text-xs text-destructive mt-1" role="alert">
          {error}
        </p>
      )}

      <div className="shrink-0 pt-3 space-y-1.5">
        <div className="flex items-end gap-2 rounded-xl border border-input bg-background/80 px-3 py-2 shadow-sm">
          <textarea
            ref={textareaRef}
            placeholder="Ask a question about your brain…"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            disabled={isLoading}
            className="flex-1 min-h-[40px] max-h-[120px] resize-none bg-transparent px-0 py-1 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Chat message input"
          />
          <Button
            type="button"
            size="icon"
            className="shrink-0 h-9 w-9 rounded-full"
            onClick={handleSend}
            disabled={isLoading || !inputValue.trim()}
            aria-label="Send message"
          >
            <SendIcon className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex justify-between items-center px-0.5">
          <p className="text-[10px] text-muted-foreground">
            Press Enter to send, Shift+Enter for a new line.
          </p>
        </div>
      </div>
    </section>
  );
}
