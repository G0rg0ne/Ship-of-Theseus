"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import * as api from "@/lib/api";
import type { PlatformStats, SystemHealth, UserAdminView } from "@/lib/api";

function AnchorIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 22V8" />
      <path d="M5 12H2a10 10 0 0 0 20 0h-3" />
      <circle cx="12" cy="5" r="3" />
    </svg>
  );
}

function LogOutIcon({ className }: { className?: string }) {
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
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" x2="9" y1="12" y2="12" />
    </svg>
  );
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export default function AdminPage() {
  const router = useRouter();
  const { token, user, isLoading: authLoading, logout } = useAuth();
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [system, setSystem] = useState<SystemHealth | null>(null);
  const [users, setUsers] = useState<UserAdminView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !token) {
      router.replace("/");
      return;
    }
    if (!authLoading && token && user && !user.is_admin) {
      router.replace("/dashboard");
      return;
    }
  }, [token, authLoading, user, router]);

  const loadData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [statsRes, systemRes, usersRes] = await Promise.all([
        api.getAdminStats(token),
        api.getSystemHealth(token),
        api.getAdminUsers(token, page, 20),
      ]);
      setStats(statsRes);
      setSystem(systemRes);
      setUsers(usersRes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load admin data");
      setStats(null);
      setSystem(null);
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [token, page]);

  useEffect(() => {
    if (token && user?.is_admin) {
      loadData();
    }
  }, [token, user?.is_admin, loadData]);

  const handleToggleAdmin = async (userId: string) => {
    if (!token) return;
    setTogglingId(userId);
    try {
      const updated = await api.toggleUserAdmin(token, userId);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? updated : u))
      );
    } catch {
      setError("Failed to toggle admin status");
    } finally {
      setTogglingId(null);
    }
  };

  const handleLogout = () => {
    logout();
    router.replace("/");
  };

  const rawName = user?.username ?? user?.email ?? "User";
  const displayName = rawName.includes("@") ? rawName.split("@")[0] : rawName;
  const initials =
    displayName.length >= 2
      ? displayName.slice(0, 2).toUpperCase()
      : displayName.slice(0, 1).toUpperCase() || "U";

  if (authLoading || !token) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Loading…</div>
      </main>
    );
  }

  if (user && !user.is_admin) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-background">
        <div className="animate-pulse text-muted-foreground">Redirecting…</div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex flex-col bg-background bg-dot-grid">
      <header className="sticky top-0 z-30 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div
          className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent"
          aria-hidden
        />
        <div className="w-full relative flex h-14 items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-4">
            <Link
              href="/dashboard"
              className="flex items-center gap-2.5 font-heading font-semibold text-foreground transition-opacity hover:opacity-90"
            >
              <AnchorIcon className="h-6 w-6 text-primary" />
              <span>Ship of Theseus</span>
            </Link>
            <Link
              href="/dashboard"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Back to Dashboard
            </Link>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border border-border bg-secondary/60 px-3 py-1">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
                {initials}
              </span>
              <span className="text-sm font-medium text-foreground">
                {displayName}
              </span>
            </div>
            <div className="h-4 w-px bg-border" aria-hidden />
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="gap-1.5 text-muted-foreground hover:text-foreground"
            >
              <LogOutIcon className="h-3.5 w-3.5" />
              Log out
            </Button>
          </div>
        </div>
      </header>

      <div className="flex-1 p-6 max-w-6xl mx-auto w-full space-y-8">
        <div>
          <h1 className="font-heading text-2xl font-semibold text-foreground">
            Admin Portal
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            System information, analytics, and user management.
          </p>
        </div>

        {error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {loading ? (
          <div className="animate-pulse text-muted-foreground">Loading admin data…</div>
        ) : (
          <>
            {/* Stats grid */}
            {stats && (
              <section>
                <h2 className="font-heading text-lg font-semibold text-foreground mb-4">
                  Platform statistics
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Total users</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.total_users}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Active users</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.active_users}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">New users (7d)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.new_users_7d}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Documents processed</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.total_documents}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Total entities</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.total_entities}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Total relationships</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.total_relationships}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Total communities</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.total_communities}</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base">Avg docs per user</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-2xl font-semibold">{stats.avg_docs_per_user}</p>
                    </CardContent>
                  </Card>
                </div>
              </section>
            )}

            {/* System health */}
            {system && (
              <section>
                <h2 className="font-heading text-lg font-semibold text-foreground mb-4">
                  System health
                </h2>
                <div className="flex flex-wrap gap-3">
                  {system.services.map((svc) => (
                    <div
                      key={svc.name}
                      className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2"
                    >
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${
                          svc.status === "healthy"
                            ? "bg-green-500"
                            : svc.status === "degraded"
                            ? "bg-amber-500"
                            : "bg-red-500"
                        }`}
                        aria-hidden
                      />
                      <span className="font-medium text-sm">{svc.name}</span>
                      <span className="text-sm text-muted-foreground capitalize">
                        {svc.status}
                      </span>
                      {svc.detail && (
                        <span className="text-xs text-muted-foreground" title={svc.detail}>
                          ({svc.detail.slice(0, 30)}
                          {svc.detail.length > 30 ? "…" : ""})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                <p className="text-sm text-muted-foreground mt-2">
                  Neo4j: {system.neo4j_node_count} nodes, {system.neo4j_edge_count} edges,{" "}
                  {system.neo4j_community_count} communities.
                </p>
              </section>
            )}

            {/* Users table */}
            <section>
              <h2 className="font-heading text-lg font-semibold text-foreground mb-4">
                Users
              </h2>
              <div className="rounded-lg border border-border overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left font-medium px-4 py-3">Username</th>
                        <th className="text-left font-medium px-4 py-3">Email</th>
                        <th className="text-left font-medium px-4 py-3">Joined</th>
                        <th className="text-left font-medium px-4 py-3">Documents</th>
                        <th className="text-left font-medium px-4 py-3">Status</th>
                        <th className="text-left font-medium px-4 py-3">Admin</th>
                        <th className="text-left font-medium px-4 py-3">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {users.length === 0 ? (
                        <tr>
                          <td colSpan={7} className="px-4 py-6 text-center text-muted-foreground">
                            No users on this page.
                          </td>
                        </tr>
                      ) : (
                        users.map((u) => (
                          <tr key={u.id} className="hover:bg-muted/30">
                            <td className="px-4 py-3 font-medium">{u.username}</td>
                            <td className="px-4 py-3 text-muted-foreground">{u.email}</td>
                            <td className="px-4 py-3">{formatDate(u.created_at)}</td>
                            <td className="px-4 py-3">{u.document_count}</td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                                  u.is_active
                                    ? "bg-green-500/15 text-green-700 dark:text-green-400"
                                    : "bg-muted text-muted-foreground"
                                }`}
                              >
                                {u.is_active ? "Active" : "Inactive"}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              {u.is_admin ? (
                                <span className="inline-flex items-center rounded-full bg-primary/15 px-2 py-0.5 text-xs font-medium text-primary">
                                  Admin
                                </span>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleToggleAdmin(u.id)}
                                disabled={togglingId !== null}
                              >
                                {togglingId === u.id
                                  ? "…"
                                  : u.is_admin
                                  ? "Demote"
                                  : "Promote"}
                              </Button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={users.length < 20}
                >
                  Next
                </Button>
                <span className="flex items-center text-sm text-muted-foreground">
                  Page {page}
                </span>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
