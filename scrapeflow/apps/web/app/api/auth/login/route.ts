import { NextResponse } from "next/server";

import {
  authUnavailable,
  forwardError,
  setSessionCookie,
  upstreamFetch,
} from "@/lib/server-api";
import type { BrowserTokenPayload, TokenPayload } from "@/lib/types";

export async function POST(request: Request): Promise<NextResponse> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return authUnavailable("Invalid JSON body");
  }

  let upstream: Response;
  try {
    upstream = await upstreamFetch("/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return authUnavailable("The ScrapeFlow API is unreachable");
  }
  if (!upstream.ok) return forwardError(upstream);

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
