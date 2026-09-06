"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api, clearToken, setToken } from "@/lib/api";
import type { UserInfo } from "@/lib/types";

interface AuthState {
  user: UserInfo | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  logoutError: string | null;
  refreshUser: () => Promise<void>;
  /** Adopt a token obtained via the SSO flow (stores it and loads the user). */
  applySession: (token: string) => Promise<boolean>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  logout: async () => {},
  logoutError: null,
  refreshUser: async () => {},
  applySession: async () => false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  /* On mount, try to restore session from stored token */
  useEffect(() => {
    const token = localStorage.getItem("tbd_token");
    if (!token) {
      setLoading(false);
      return;
    }
    api.auth
      .me()
      .then(setUser)
      .catch(() => {
        clearToken();
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.auth.login({ username, password });
    setToken(res.access_token);
    const me = await api.auth.me();
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    setLogoutError(null);
    try {
      await api.auth.logout();
      clearToken();
      setUser(null);
    } catch {
      setLogoutError("Sign-out was not confirmed. Please retry.");
    }
  }, []);

  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === "tbd_token" && !event.newValue) setUser(null);
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const refreshUser = useCallback(async () => {
    try {
      const me = await api.auth.me();
      setUser(me);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
        setUser(null);
      }
    }
  }, []);

  const applySession = useCallback(async (token: string): Promise<boolean> => {
    setToken(token);
    try {
      const me = await api.auth.me();
      setUser(me);
      return true;
    } catch {
      clearToken();
      return false;
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, logoutError, refreshUser, applySession }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
