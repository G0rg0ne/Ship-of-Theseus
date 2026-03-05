"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import * as api from "@/lib/api";

const TOKEN_KEY = "ship_token";
const USER_KEY = "ship_user";

type AuthContextValue = {
  token: string | null;
  user: api.UserResponse | null;
  isLoading: boolean;
  setToken: (token: string | null, user: api.UserResponse | null) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<api.UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const setToken = useCallback(
    (newToken: string | null, newUser: api.UserResponse | null) => {
      if (typeof window === "undefined") return;
      if (newToken) {
        localStorage.setItem(TOKEN_KEY, newToken);
        if (newUser) localStorage.setItem(USER_KEY, JSON.stringify(newUser));
      } else {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
      }
      setTokenState(newToken);
      setUser(newUser);
    },
    []
  );

  const logout = useCallback(() => {
    setToken(null, null);
  }, [setToken]);

  const refreshUser = useCallback(async () => {
    const t = localStorage.getItem(TOKEN_KEY);
    if (!t) return;
    try {
      const u = await api.getMe(t);
      setUser(u);
      localStorage.setItem(USER_KEY, JSON.stringify(u));
    } catch {
      logout();
    }
  }, [logout]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const t = localStorage.getItem(TOKEN_KEY);
    const u = localStorage.getItem(USER_KEY);
    setTokenState(t);
    setUser(u ? (JSON.parse(u) as api.UserResponse) : null);
    setIsLoading(false);
  }, []);

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
