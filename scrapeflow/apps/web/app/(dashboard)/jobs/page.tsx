"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Select,
  Spinner,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import {
  formatDate,
  formatDuration,
  isActiveStatus,
  shortId,
  statusTone,
  truncateMiddle,
} from "@/lib/format";
import type { JobList, JobStatus } from "@/lib/types";

const PAGE_SIZE = 25;
const STATUS_OPTIONS: Array<{ value: "" | JobStatus; label: string }> = [
  { value: "", label: "All statuses" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Running" },
  { value: "succeeded", label: "Succeeded" },
  { value: "failed", label: "Failed" },
  { value: "cancelled", label: "Cancelled" },
  { value: "timed_out", label: "Timed out" },
];

export default function JobsPage(): ReactNode {
  const { requestJson } = useAuth();
  const [data, setData] = useState<JobList | null>(null);
  const [status, setStatus] = useState<"" | JobStatus>("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const load = useCallback(
    async (silent = false): Promise<void> => {
      if (inFlight.current) return;
      inFlight.current = true;
      if (!silent) setLoading(true);
      try {
        const query = new URLSearchParams({
          limit: String(PAGE_SIZE),
          offset: String(offset),
        });
        if (status) query.set("status", status);
        const result = await requestJson<JobList>(`/v1/jobs?${query.toString()}`);
        setData(result);
        setError(null);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "Unable to load jobs");
      } finally {
        inFlight.current = false;
        if (!silent) setLoading(false);
      }
    },
    [offset, requestJson, status],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const hasActive = data?.items.some((job) => isActiveStatus(job.status)) ?? false;
  useEffect(() => {
    if (!hasActive) return;
    const timer = setInterval(() => {
      void load(true);
    }, 5_000);
    return () => clearInterval(timer);
  }, [hasActive, load]);

  const total = data?.total ?? 0;
  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Jobs</h1>
          <p className="mt-1 text-sm text-slate-500">
            Scrapes and automations for this organisation. Active jobs refresh every five
            seconds.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select
            aria-label="Filter by status"
            className="w-44"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as "" | JobStatus);
              setOffset(0);
            }}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value || "all"} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Button variant="secondary" onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? <Alert>{error}</Alert> : null}

      <Card>
        <CardHeader
          title="Recent jobs"
          description={`${pageStart}–${pageEnd} of ${total}`}
          actions={
            <>
              <Link href="/scrape">
                <Button size="sm">New scrape</Button>
              </Link>
              <Link href="/automate">
                <Button size="sm" variant="secondary">
                  New automation
                </Button>
              </Link>
            </>
          }
        />
        {loading && !data ? (
          <div className="flex justify-center px-5 py-12 text-slate-500">
            <Spinner className="h-6 w-6" />
          </div>
        ) : null}
        {!loading && data && data.items.length === 0 ? (
          <EmptyState
            title="No jobs yet"
            description="Submit a scrape or automation and it will appear here with status, logs, artifacts, and exports."
            action={
              <Link href="/scrape">
                <Button size="sm">Run your first scrape</Button>
              </Link>
            }
          />
        ) : null}
        {data && data.items.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-3 py-3 font-medium">Kind</th>
                  <th className="px-3 py-3 font-medium">URL</th>
                  <th className="px-3 py-3 font-medium">Created</th>
                  <th className="px-3 py-3 font-medium">Duration</th>
                  <th className="px-5 py-3 text-right font-medium">Job</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((job) => (
                  <tr key={job.id} className="hover:bg-slate-50">
                    <td className="whitespace-nowrap px-5 py-3">
                      <Badge tone={statusTone(job.status)}>{job.status}</Badge>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                      {job.kind}
                    </td>
                    <td className="max-w-md px-3 py-3">
                      <Link
                        href={`/jobs/${job.id}`}
                        className="text-slate-800 underline decoration-slate-300 underline-offset-2 hover:text-slate-950"
                        title={job.url}
                      >
                        {truncateMiddle(job.url, 72)}
                      </Link>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                      {formatDate(job.created_at)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                      {formatDuration(job.duration_ms)}
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 text-right">
                      <Link
                        href={`/jobs/${job.id}`}
                        className="text-sm font-medium text-slate-900 underline"
                      >
                        {shortId(job.id)}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
        <div className="flex items-center justify-between border-t border-slate-100 px-5 py-3">
          <p className="text-xs text-slate-500">
            Page {Math.floor(offset / PAGE_SIZE) + 1}
          </p>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
