"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  FileText,
  Network,
  Brain,
  Users,
  Anchor,
} from "lucide-react";
import { AuthCard } from "@/components/auth/AuthCard";
import { useAuth } from "@/hooks/useAuth";

const features = [
  {
    icon: FileText,
    label: "Upload PDFs",
    description: "Drag and drop or browse to add documents.",
  },
  {
    icon: Network,
    label: "Extract knowledge graphs",
    description: "Entities, relationships, and context from your docs.",
  },
  {
    icon: Brain,
    label: "Build your brain",
    description: "Merge graphs into a personal knowledge base.",
  },
  {
    icon: Users,
    label: "Share & explore",
    description: "Communities and insights from your graph.",
  },
];

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 12 },
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
    <div className="min-h-screen w-full bg-welcome-gradient">
      <main className="min-h-screen flex flex-col lg:flex-row lg:items-center lg:justify-center lg:max-w-7xl lg:mx-auto gap-10 lg:gap-12 px-6 py-12 lg:px-12 lg:py-16">
        {/* Left: Hero panel – room for large demo section */}
      <motion.div
        className="relative flex flex-col justify-center lg:w-[min(100%,56rem)] lg:max-w-[65%] lg:shrink-0"
        initial="hidden"
        animate="show"
        variants={container}
      >
        <div className="relative z-10 max-w-4xl">
          <motion.div variants={item} className="flex items-center gap-3">
            <span
              className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/20 text-primary"
              aria-hidden
            >
              <Anchor className="h-6 w-6" />
            </span>
            <h1 className="text-3xl font-bold tracking-tight text-foreground lg:text-4xl">
              Ship of Theseus
            </h1>
          </motion.div>
          <motion.p
            variants={item}
            className="mt-4 text-lg text-muted-foreground lg:text-xl"
          >
            Build your knowledge brain from documents. Upload PDFs, extract
            entities and relationships into a graph, and explore your personal
            knowledge base.
          </motion.p>

          <motion.ul
            variants={container}
            className="mt-10 space-y-4"
          >
            {features.map(({ icon: Icon, label, description }) => (
              <motion.li
                key={label}
                variants={item}
                className="flex gap-4 rounded-lg border border-white/5 bg-white/5 p-4 backdrop-blur-sm"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                  <Icon className="h-5 w-5" />
                </span>
                <div>
                  <span className="font-medium text-foreground">{label}</span>
                  <p className="text-sm text-muted-foreground">{description}</p>
                </div>
              </motion.li>
            ))}
          </motion.ul>

          {/* Knowledge Brain demo – prominent showcase */}
          <motion.p
            variants={item}
            className="mt-12 mb-3 text-sm font-medium uppercase tracking-wider text-primary/90"
          >
            See it in action
          </motion.p>
          <motion.div
            variants={item}
            className="overflow-hidden rounded-2xl border border-white/15 bg-black/30 shadow-2xl ring-1 ring-white/5"
            style={{
              boxShadow:
                "0 0 0 1px rgba(255,255,255,0.06), 0 25px 50px -12px rgba(0,0,0,0.5), 0 0 40px -12px hsl(var(--primary) / 0.15)",
            }}
          >
            <div className="relative aspect-[4/3] w-full min-h-[380px] max-w-4xl lg:min-h-[420px]">
              <img
                src="/SS_v3.png"
                alt="Example knowledge brain visualization"
                className="h-full w-full object-contain"
                onError={(e) => {
                  e.currentTarget.style.display = "none";
                  const fallback = e.currentTarget.nextElementSibling;
                  if (fallback instanceof HTMLElement) {
                    fallback.style.display = "flex";
                  }
                }}
              />
              <div
                className="absolute inset-0 hidden flex-col items-center justify-center gap-2 bg-card/80 text-muted-foreground"
                aria-hidden
              >
                <Brain className="h-16 w-16 opacity-50" />
                <span className="text-sm">Example brain (image unavailable)</span>
              </div>
            </div>
          </motion.div>
        </div>
      </motion.div>

      {/* Right: Auth panel – fixed width, sits next to hero */}
      <motion.aside
        className="flex w-full flex-col items-center justify-center lg:w-auto lg:min-w-[380px] lg:max-w-[400px] lg:shrink-0"
        initial={{ opacity: 0, x: 24 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.4, delay: 0.2 }}
      >
        <div className="w-full max-w-sm lg:max-w-none">
          <div className="glass-panel p-8">
            <AuthCard />
          </div>
        </div>
      </motion.aside>
      </main>
    </div>
  );
}
