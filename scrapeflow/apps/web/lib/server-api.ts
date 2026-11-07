import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export const REFRESH_COOKIE = "sf_refresh";
const SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

export function apiBaseUrl(): string {
  const value = process.env.API_BASE_URL ?? "http://localhost:8000";
  return value.replace(/\/+$/, "");
}

export async function upstreamFetch(path: string, init: RequestInit): Promise<Response> {
  return fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
  });
}

export async function sessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(REFRESH_COOKIE)?.value ?? null;
}

export function setSessionCookie(response: NextResponse, token: string): void {
  response.cookies.set(REFRESH_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_MAX_AGE_SECONDS,
  });
}

export function clearSessionCookie(response: NextResponse): void {
  response.cookies.set(REFRESH_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
}

export async function forwardError(response: Response): Promise<NextResponse> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = { error: { code: "UPSTREAM_ERROR", message: "Upstream request failed" } };
  }
  return NextResponse.json(payload, { status: response.status });
}

export function authUnavailable(message: string): NextResponse {
  return NextResponse.json(
    { error: { code: "UNAUTHORIZED", message } },
    { status: 401 },
  );
}
