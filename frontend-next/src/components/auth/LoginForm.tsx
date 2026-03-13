"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login, resendVerification, ApiError } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

export function LoginForm() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [needsVerification, setNeedsVerification] = useState(false);
  const [verifyEmail, setVerifyEmail] = useState("");
  const [verifyMessage, setVerifyMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { setToken } = useAuth();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setNeedsVerification(false);
    setVerifyMessage(null);
    setLoading(true);
    try {
      const { token, user, expires_in } = await login(username, password);
      setToken(token, user, expires_in);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setNeedsVerification(true);
          setError(err.message);
        } else {
          setError(err.message);
        }
      } else if (
        err instanceof TypeError && err.message.includes("fetch")
      ) {
        const apiUrl =
          process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
        setError(
          `Cannot reach the server at ${apiUrl}. Please ensure the backend is running and that this URL is reachable from your browser.`
        );
      } else {
        setError(err instanceof Error ? err.message : "Login failed");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleResend() {
    setVerifyMessage(null);
    setError("");
    setLoading(true);
    try {
      const data = await resendVerification(verifyEmail);
      setVerifyMessage(data.message);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "Failed to resend email");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <p
          className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}
      <div className="space-y-2">
        <Label htmlFor="login-username">Username</Label>
        <Input
          id="login-username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          autoComplete="username"
          disabled={loading}
          className={cn(error && "border-destructive/50 focus-visible:ring-destructive/40")}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="login-password">Password</Label>
        <Input
          id="login-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
          disabled={loading}
          className={cn(error && "border-destructive/50 focus-visible:ring-destructive/40")}
        />
      </div>
      <Button type="submit" className="w-full glow-primary-hover" disabled={loading}>
        {loading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Signing in…
          </>
        ) : (
          "Sign in"
        )}
      </Button>

      {needsVerification && (
        <div className="rounded-lg border border-border/60 bg-muted/30 p-3 space-y-2">
          <p className="text-sm text-muted-foreground">
            Didn&apos;t get the email? Enter your email address and we&apos;ll resend the verification link.
          </p>
          {verifyMessage && (
            <p className="text-sm text-primary">{verifyMessage}</p>
          )}
          <div className="flex gap-2">
            <Input
              type="email"
              value={verifyEmail}
              onChange={(e) => setVerifyEmail(e.target.value)}
              placeholder="you@example.com"
              required
              disabled={loading}
            />
            <Button type="button" variant="secondary" disabled={loading} onClick={handleResend}>
              Resend
            </Button>
          </div>
        </div>
      )}
    </form>
  );
}
