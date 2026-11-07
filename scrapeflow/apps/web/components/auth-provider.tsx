"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ApiError, errorFromResponse } from "@/lib/api";
import type { BrowserTokenPayload, Me } from "@/lib/types";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface LoginInput {
  email: string;
  password: string;
  orgSlug?: string;
}

interface SignupInput {
  orgName: string;
  email: string;
  password: string;
  displayName?: string;
}

interface AuthContextValue {
  status: AuthStatus;
  me: Me | null;
  orgId: string | null;
  role: string | null;
  login: (input: LoginInput) => Promise<void>;
  signup: (input: SignupInput) => Promise<void>;
  logout: () => Promise<void>;
  request: (path: string, init?: RequestInit) => Promise<Response>;
  requestJson: <T>(path: string, init?: RequestInit) => Promise<T>;
  refreshSession: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

async function fetchMe(token: string): Promise<Me> {
  const response = await fetch("/api/proxy/v1/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) throw await errorFromResponse(response);
  return (await response.json()) as Me;
}

export function AuthProvider({ children }: { children: ReactNode }): ReactNode {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const tokenRef = useRef<string | null>(null);
  const refreshPromiseRef = useRef<Promise<string | null> | null>(null);

  const refreshSession = useCallback(async (): Promise<string | null> => {
    if (refreshPromiseRef.current) return refreshPromiseRef.current;
    const promise = (async () => {
      try {
        const response = await fetch("/api/auth/refresh", {
          method: "POST",
          cache: "no-store",
        });
        if (!response.ok) {
          tokenRef.current = null;
          return null;
        }
        const payload = (await response.json()) as BrowserTokenPayload;
        tokenRef.current = payload.access_token;
        setOrgId(payload.org_id);
        setRole(payload.role);
        return payload.access_token;
      } catch {
        tokenRef.current = null;
        return null;
      }
    })().finally(() => {
      refreshPromiseRef.current = null;
    });
    refreshPromiseRef.current = promise;
    return promise;
  }, []);

  const adopt = useCallback(async (payload: BrowserTokenPayload): Promise<void> => {
    tokenRef.current = payload.access_token;
    setOrgId(payload.org_id);
    setRole(payload.role);
    const profile = await fetchMe(payload.access_token);
    setMe(profile);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const token = await refreshSession();
      if (cancelled) return;
      if (!token) {
        setStatus("anonymous");
        return;
      }
      try {
        const profile = await fetchMe(token);
        if (cancelled) return;
        setMe(profile);
        setStatus("authenticated");
      } catch {
        if (!cancelled) {
          tokenRef.current = null;
          setStatus("anonymous");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshSession]);

  const login = useCallback(
    async (input: LoginInput): Promise<void> => {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: input.email,
          password: input.password,
          org_slug: input.orgSlug || null,
        }),
      });
      if (!response.ok) throw await errorFromResponse(response);
      await adopt((await response.json()) as BrowserTokenPayload);
    },
    [adopt],
  );

  const signup = useCallback(
    async (input: SignupInput): Promise<void> => {
      const response = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          org_name: input.orgName,
          email: input.email,
          password: input.password,
          display_name: input.displayName ?? "",
          tos_accepted: true,
        }),
      });
      if (!response.ok) throw await errorFromResponse(response);
      await adopt((await response.json()) as BrowserTokenPayload);
    },
    [adopt],
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      tokenRef.current = null;
      setMe(null);
      setOrgId(null);
      setRole(null);
      setStatus("anonymous");
    }
  }, []);

  const request = useCallback(
    async (path: string, init?: RequestInit): Promise<Response> => {
      const token = tokenRef.current ?? (await refreshSession());
      if (!token) throw new ApiError(401, "UNAUTHORIZED", "Your session has expired");

      const send = async (bearer: string): Promise<Response> => {
        const headers = new Headers(init?.headers);
        headers.set("Authorization", `Bearer ${bearer}`);
        return fetch(`/api/proxy${path}`, {
          ...init,
          headers,
          cache: "no-store",
        });
      };

      let response = await send(token);
      if (response.status === 401) {
        const refreshed = await refreshSession();
        if (refreshed) response = await send(refreshed);
      }
      return response;
    },
    [refreshSession],
  );

  const requestJson = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const response = await request(path, init);
      if (!response.ok) throw await errorFromResponse(response);
      return (await response.json()) as T;
    },
    [request],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      me,
      orgId,
      role,
      login,
      signup,
      logout,
      request,
      requestJson,
      refreshSession,
    }),
    [status, me, orgId, role, login, signup, logout, request, requestJson, refreshSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
