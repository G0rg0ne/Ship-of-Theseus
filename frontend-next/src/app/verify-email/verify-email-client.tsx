"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { verifyEmail, ApiError } from "@/lib/api";

export default function VerifyEmailClient() {
  const searchParams = useSearchParams();
  const token = useMemo(() => searchParams.get("token"), [searchParams]);
  const [status, setStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Missing verification token.");
      return;
    }

    let cancelled = false;
    setStatus("loading");
    verifyEmail(token)
      .then((res) => {
        if (cancelled) return;
        setStatus("success");
        setMessage(res.message || "Email verified. You can sign in now.");
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        if (err instanceof ApiError) setMessage(err.message);
        else setMessage(err instanceof Error ? err.message : "Verification failed");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <main className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-xl border border-border/60 bg-card/60 p-6 backdrop-blur">
        <h1 className="text-xl font-semibold">Verify email</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {status === "loading" ? "Verifying your email…" : message || ""}
        </p>
        {status === "success" && (
          <a
            href="/"
            className="mt-4 inline-flex text-sm text-primary underline underline-offset-4"
          >
            Go to sign in
          </a>
        )}
      </div>
    </main>
  );
}

