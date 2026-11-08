#!/usr/bin/env node
// Minimal ScrapeFlow API client using the built-in fetch (Node 18+).
//
//   SCRAPEFLOW_BASE_URL=https://api.example.com \
//   SCRAPEFLOW_API_KEY=sf_live_... node examples/node_client.mjs https://example.com

import { randomUUID } from "node:crypto";

const BASE_URL = (process.env.SCRAPEFLOW_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const API_KEY = process.env.SCRAPEFLOW_API_KEY ?? "";

class ApiError extends Error {
  constructor(status, body) {
    super(`${status} ${body?.error?.code ?? "UNKNOWN"} (request_id=${body?.request_id})`);
    this.status = status;
    this.code = body?.error?.code;
    this.requestId = body?.request_id;
  }
}

async function request(method, path, payload, idempotencyKey) {
  const headers = {
    Authorization: `Bearer ${API_KEY}`,
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  const response = await fetch(BASE_URL + path, {
    method,
    headers,
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(response.status, body);
  return body;
}

async function scrapeAndWait(url, timeoutMs = 120_000) {
  const accepted = await request(
    "POST",
    "/v1/scrape",
    { url, render_js: false, extract: { text: true, links: true } },
    randomUUID(),
  );
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const job = await request("GET", `/v1/jobs/${accepted.job_id}`);
    if (["succeeded", "failed", "cancelled", "timed_out"].includes(job.status)) return job;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error(`job ${accepted.job_id} did not finish in ${timeoutMs}ms`);
}

async function main() {
  if (!API_KEY) {
    console.error("Set SCRAPEFLOW_API_KEY to a key with the jobs:write scope.");
    process.exit(2);
  }
  const target = process.argv[2] ?? "https://example.com";
  const job = await scrapeAndWait(target);
  console.log(JSON.stringify(job, null, 2));
  process.exit(job.status === "succeeded" ? 0 : 1);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
