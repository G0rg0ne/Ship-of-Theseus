"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { FileText, Network, Brain, Users } from "lucide-react";
import { AuthCard } from "@/components/auth/AuthCard";
import { NodeConstellation } from "@/components/NodeConstellation";
import { useAuth } from "@/hooks/useAuth";

const journeySteps = [
  { icon: FileText, label: "Upload" },
  { icon: Network, label: "Extract" },
  { icon: Brain, label: "Build" },
  { icon: Users, label: "Explore" },
];

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.06, delayChildren: 0.05 },
  },
};

const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0 },
};

export default function AuthPage() {
  const { token, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && token) {
      router.replace("/dashboard");
    }
  }, [token, isLoading, router]);

  if (isLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </main>
    );
  }

  if (token) {
    return null;
  }

  return (
    <div className="min-h-screen w-full bg-welcome-gradient bg-dot-grid">
      <main className="min-h-screen flex flex-col lg:flex-row lg:items-center lg:justify-between lg:max-w-7xl lg:mx-auto gap-10 lg:gap-8 px-6 py-12 lg:px-12 lg:py-16">
        {/* Left: Hero with constellation background */}
        <motion.div
          className="relative flex flex-col justify-center lg:w-[min(100%,52rem)] lg:max-w-[62%] lg:shrink-0 min-h-[320px] lg:min-h-[480px]"
          initial="hidden"
          animate="show"
          variants={container}
        >
          <div className="absolute inset-0 lg:inset-y-0 lg:left-0 lg:right-1/3 lg:mr-8">
            <NodeConstellation />
          </div>
          <div className="relative z-10 max-w-xl">
            <motion.h1
              variants={item}
              className="font-heading text-4xl font-semibold tracking-tight text-foreground lg:text-5xl"
              style={{
                textShadow: "0 0 40px hsl(38 92% 50% / 0.15)",
              }}
            >
              Ship of Theseus
            </motion.h1>
            <motion.p
              variants={item}
              className="mt-4 text-base text-muted-foreground lg:text-lg max-w-md"
            >
              Build your knowledge brain from documents. Extract entities and
              relationships into a graph, then explore your personal knowledge
              base.
            </motion.p>
            <motion.p variants={item} className="mt-3 max-w-md">
              <Link
                href="/how-it-works"
                className="text-sm font-medium text-primary hover:underline underline-offset-4"
              >
                How it works?
              </Link>
              <span className="text-sm text-muted-foreground">
                {" "}
                — see the pipeline, dashboard, and Q&amp;A before you register.
              </span>
            </motion.p>

            {/* Horizontal journey strip */}
            <motion.div
              variants={container}
              className="mt-10 flex flex-wrap items-center gap-4 sm:gap-6"
            >
              {journeySteps.map(({ icon: Icon, label }, i) => (
                <motion.div
                  key={label}
                  variants={item}
                  className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
                >
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <Icon className="h-4 w-4" />
                  </span>
                  <span className="text-sm font-medium">{label}</span>
                  {i < journeySteps.length - 1 && (
                    <span
                      className="hidden sm:block w-6 h-px bg-border ml-1"
                      aria-hidden
                    />
                  )}
                </motion.div>
              ))}
            </motion.div>
          </div>
        </motion.div>

        {/* Right: Auth panel with left accent bar */}
        <motion.aside
          className="flex w-full flex-col items-center justify-center lg:w-auto lg:min-w-[360px] lg:max-w-[400px] lg:shrink-0"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.35, delay: 0.15 }}
        >
          <div className="w-full max-w-sm lg:max-w-none relative">
            <div
              className="absolute left-0 top-0 bottom-0 w-[3px] rounded-l-lg bg-primary/70"
              aria-hidden
            />
            <div className="rounded-xl border border-border bg-card pl-5 pr-8 py-8 shadow-2xl relative overflow-hidden noise-overlay">
              <AuthCard />
            </div>
          </div>
        </motion.aside>
      </main>
    </div>
  );
}
