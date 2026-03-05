"use client";

import useSWR from "swr";
import * as api from "@/lib/api";

function fetcher([url, token]: [string, string | null]) {
  if (!token) return Promise.resolve(null);
  return api.getUserBrain(token);
}

export function useBrain(token: string | null) {
  const { data: brain, error, isLoading, mutate } = useSWR(
    ["/api/community/brain", token],
    fetcher,
    { revalidateOnFocus: false }
  );

  const refresh = async () => {
    if (!token) return null;
    try {
      const updated = await api.triggerCommunityDetection(token);
      mutate(updated, false);
      return updated;
    } catch {
      await mutate();
      return null;
    }
  };

  const remove = async () => {
    if (!token) return;
    await api.deleteUserBrain(token);
    mutate(null, false);
  };

  return {
    brain: brain ?? null,
    isLoading,
    error,
    refresh,
    remove,
    mutate,
  };
}
