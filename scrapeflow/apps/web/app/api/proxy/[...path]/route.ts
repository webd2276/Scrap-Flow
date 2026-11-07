import { NextResponse } from "next/server";

import { apiBaseUrl } from "@/lib/server-api";

export const runtime = "nodejs";

const SEGMENT = /^[A-Za-z0-9._~-]+$/;
const PASS_THROUGH_HEADERS = new Set([
  "authorization",
  "content-type",
  "accept",
  "idempotency-key",
]);

function allowedPath(path: string[]): boolean {
  if (path.length < 2 || path[0] !== "v1") return false;
  return path.every(
    (segment) => SEGMENT.test(segment) && segment !== "." && segment !== "..",
  );
}

function responseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  upstream.headers.forEach((value, name) => {
    const lowered = name.toLowerCase();
    if (
      PASS_THROUGH_HEADERS.has(lowered) ||
      lowered === "content-type" ||
      lowered === "content-disposition" ||
      lowered === "cache-control" ||
      lowered === "retry-after" ||
      lowered === "x-request-id" ||
      lowered === "idempotent-replay" ||
      lowered.startsWith("x-ratelimit-") ||
      lowered.startsWith("x-quota-") ||
      lowered.startsWith("x-concurrency-")
    ) {
      headers.set(name, value);
    }
  });
  return headers;
}

async function handle(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
  method: string,
): Promise<Response> {
  const { path } = await context.params;
  if (!allowedPath(path)) {
    return NextResponse.json(
      { error: { code: "NOT_FOUND", message: "Unknown API path" } },
      { status: 404 },
    );
  }

  const incoming = new URL(request.url);
  const target = `${apiBaseUrl()}/${path
    .map((segment) => encodeURIComponent(segment))
    .join("/")}${incoming.search}`;

  const headers = new Headers();
  for (const [name, value] of request.headers.entries()) {
    if (PASS_THROUGH_HEADERS.has(name.toLowerCase())) headers.set(name, value);
  }

  const hasBody = method !== "GET" && method !== "HEAD";
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      redirect: "follow",
    });
  } catch {
    return NextResponse.json(
      { error: { code: "UPSTREAM_ERROR", message: "The ScrapeFlow API is unreachable" } },
      { status: 502 },
    );
  }

  if (upstream.status === 204 || upstream.status === 304) {
    return new Response(null, { status: upstream.status, headers: responseHeaders(upstream) });
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders(upstream),
  });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export function GET(request: Request, context: RouteContext): Promise<Response> {
  return handle(request, context, "GET");
}

export function POST(request: Request, context: RouteContext): Promise<Response> {
  return handle(request, context, "POST");
}

export function PATCH(request: Request, context: RouteContext): Promise<Response> {
  return handle(request, context, "PATCH");
}

export function DELETE(request: Request, context: RouteContext): Promise<Response> {
  return handle(request, context, "DELETE");
}
