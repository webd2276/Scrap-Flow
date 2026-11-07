import { NextResponse } from "next/server";

import { clearSessionCookie, sessionToken, upstreamFetch } from "@/lib/server-api";

export async function POST(): Promise<NextResponse> {
  const refreshToken = await sessionToken();
  if (refreshToken) {
    try {
      await upstreamFetch("/v1/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch {
      // The local session is cleared even if the API is unreachable.
    }
  }
  const response = NextResponse.json({ status: "logged_out" });
  clearSessionCookie(response);
  return response;
}
