import { Suspense } from "react";
import VerifyEmailClient from "./verify-email-client";

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen flex items-center justify-center bg-background px-4">
          <div className="w-full max-w-md rounded-xl border border-border/60 bg-card/60 p-6 backdrop-blur">
            <h1 className="text-xl font-semibold">Verify email</h1>
            <p className="mt-2 text-sm text-muted-foreground">Loading…</p>
          </div>
        </main>
      }
    >
      <VerifyEmailClient />
    </Suspense>
  );
}
