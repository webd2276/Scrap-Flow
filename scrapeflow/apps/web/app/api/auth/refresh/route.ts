import { NextResponse } from "next/server";

import {
  authUnavailable,
  clearSessionCookie,
  forwardError,
  sessionToken,
  setSessionCookie,
  upstreamFetch,
} from "@/lib/server-api";
import type { BrowserTokenPayload, TokenPayload } from "@/lib/types";

export async function POST(): Promise<NextResponse> {
  const refreshToken = await sessionToken();
  if (!refreshToken) return authUnavailable("No session");

  let upstream: Response;
  try {
    upstream = await upstreamFetch("/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  } catch {
    return authUnavailable("The ScrapeFlow API is unreachable");
  }
  if (!upstream.ok) {
    const response = await forwardError(upstream);
    clearSessionCookie(response);
    return response;
  }

  const tokens = (await upstream.json()) as TokenPayload;
  const payload: BrowserTokenPayload = {
    access_token: tokens.access_token,
    expires_in: tokens.expires_in,
    user_id: tokens.user_id,
    org_id: tokens.org_id,
    role: tokens.role,
  };
  const response = NextResponse.json(payload);
  setSessionCookie(response, tokens.refresh_token);
  return response;
}
