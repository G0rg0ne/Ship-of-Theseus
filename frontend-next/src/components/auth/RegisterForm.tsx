"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { register, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

export function RegisterForm() {
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(username, email, password);
      setUsername("");
      setEmail("");
      setPassword("");
      setError("Account created. Sign in with your username and password.");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof TypeError && err.message.includes("fetch")) {
        setError("Cannot reach the server. Is the backend running at the API URL?");
      } else {
        setError(err instanceof Error ? err.message : "Registration failed");
      }
    } finally {
      setLoading(false);
    }
  }

  const isSuccess = error?.includes("Account created");
  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <p
          className={cn(
            "rounded-lg px-3 py-2 text-sm",
            isSuccess
              ? "border border-primary/30 bg-primary/10 text-primary"
              : "border border-destructive/30 bg-destructive/10 text-destructive"
          )}
          role="alert"
        >
          {error}
        </p>
      )}
      <div className="space-y-2">
        <Label htmlFor="reg-username">Username</Label>
        <Input
          id="reg-username"
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          autoComplete="username"
          disabled={loading}
          className={cn(!isSuccess && error && "border-destructive/50 focus-visible:ring-destructive/40")}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="reg-email">Email</Label>
        <Input
          id="reg-email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoComplete="email"
          disabled={loading}
          className={cn(!isSuccess && error && "border-destructive/50 focus-visible:ring-destructive/40")}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="reg-password">Password (min 8 characters)</Label>
        <Input
          id="reg-password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          autoComplete="new-password"
          disabled={loading}
          className={cn(!isSuccess && error && "border-destructive/50 focus-visible:ring-destructive/40")}
        />
      </div>
      <Button type="submit" className="w-full glow-primary-hover" disabled={loading}>
        {loading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Creating account…
          </>
        ) : (
          "Create account"
        )}
      </Button>
    </form>
  );
}
