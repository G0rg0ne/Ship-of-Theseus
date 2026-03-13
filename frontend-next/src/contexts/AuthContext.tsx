"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import * as api from "@/lib/api";

type AuthContextValue = {
  token: string | null;
  user: api.UserResponse | null;
  isLoading: boolean;
  setToken: (
    token: string | null,
    user: api.UserResponse | null,
    expiresInSeconds?: number | null
  ) => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** Refresh access token ~80% of expiry (e.g. 12 min for 15 min token). */
const REFRESH_AT_FRACTION = 0.8;

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<api.UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionGenRef = useRef(0);

  const scheduleRefresh = useCallback((expiresInSeconds: number) => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    const delayMs = Math.max(1000, expiresInSeconds * REFRESH_AT_FRACTION * 1000);
    refreshTimerRef.current = setTimeout(async () => {
      refreshTimerRef.current = null;
      const gen = sessionGenRef.current;
      try {
        const data = await api.refreshToken();
        const u = await api.getMe(data.access_token);
        if (sessionGenRef.current !== gen) return;
        setToken(data.access_token, u, data.expires_in);
      } catch {
        if (sessionGenRef.current !== gen) return;
        setTokenState(null);
        setUser(null);
      }
    }, delayMs);
  }, []);

  const setToken = useCallback(
    (newToken: string | null, newUser: api.UserResponse | null, expiresInSeconds?: number | null) => {
      setTokenState(newToken);
      setUser(newUser);

      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }

      if (newToken && typeof expiresInSeconds === "number") {
        scheduleRefresh(expiresInSeconds);
      }
    },
    [scheduleRefresh]
  );

  const logout = useCallback(async () => {
    sessionGenRef.current += 1;
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    try {
      await api.logout();
    } catch (err) {
      setTokenState(null);
      setUser(null);
      throw err;
    }
    setTokenState(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    if (!token) return;
    const gen = sessionGenRef.current;
    const currentToken = token;
    try {
      const u = await api.getMe(currentToken);
      if (sessionGenRef.current !== gen) return;
      setUser(u);
    } catch {
      if (sessionGenRef.current !== gen) return;
      await logout();
    }
  }, [token, logout]);

  /** On mount: try to restore session via refresh cookie (no localStorage). */
  useEffect(() => {
    let cancelled = false;
    const gen = sessionGenRef.current;
    (async () => {
      try {
        const data = await api.refreshToken();
        if (cancelled || sessionGenRef.current !== gen) return;
        const u = await api.getMe(data.access_token);
        if (cancelled || sessionGenRef.current !== gen) return;
        setToken(data.access_token, u, data.expires_in);
      } catch {
        if (!cancelled && sessionGenRef.current === gen) {
          setTokenState(null);
          setUser(null);
        }
      } finally {
        if (!cancelled && sessionGenRef.current === gen) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current);
    };
  }, [setToken]);

  const value: AuthContextValue = {
    token,
    user,
    isLoading,
    setToken,
    logout,
    refreshUser,
  };

  return (
    <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx == null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
