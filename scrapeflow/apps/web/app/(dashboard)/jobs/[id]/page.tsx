"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useAuth } from "@/components/auth-provider";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  CopyButton,
  EmptyState,
  Spinner,
} from "@/components/ui";
import { ApiError, errorFromResponse } from "@/lib/api";
import { downloadResponse } from "@/lib/download";
import {
  formatBytes,
  formatDate,
  formatDuration,
  isActiveStatus,
  prettyJson,
  statusTone,
} from "@/lib/format";
import type { Artifact, Job, JobEvent } from "@/lib/types";

function ArtifactCard({
  artifact,
  request,
}: {
  artifact: Artifact;
  request: (path: string, init?: RequestInit) => Promise<Response>;
}): ReactNode {
  const [preview, setPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const isImage = artifact.content_type.startsWith("image/");

  useEffect(() => {
    if (!isImage) return;
    let active = true;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const response = await request(artifact.download_url);
        if (!response.ok) throw await errorFromResponse(response);
        objectUrl = URL.createObjectURL(await response.blob());
        if (active) setPreview(objectUrl);
      } catch (caught) {
        if (active) {
          setPreviewError(
            caught instanceof ApiError ? caught.message : "Unable to load preview",
          );
        }
      }
    })();
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [artifact.download_url, isImage, request]);

  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-slate-800">{artifact.filename}</p>
          <p className="text-xs text-slate-500">
            {artifact.kind} · {artifact.content_type} · {formatBytes(artifact.size_bytes)}
          </p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          loading={downloading}
          onClick={async () => {
            setDownloading(true);
            try {
              const response = await request(artifact.download_url);
              await downloadResponse(response, artifact.filename);
            } catch (caught) {
              setPreviewError(
                caught instanceof ApiError ? caught.message : "Download failed",
              );
            } finally {
              setDownloading(false);
            }
          }}
        >
          Download
        </Button>
      </div>
      {isImage ? (
        <div className="mt-3">
          {preview ? (
            // Blob previews cannot use next/image without extra configuration.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={preview}
              alt={`Screenshot ${artifact.filename}`}
              className="max-h-96 w-auto rounded border border-slate-200"
            />
          ) : previewError ? (
            <p className="text-xs text-rose-700">{previewError}</p>
          ) : (
            <div className="flex h-24 items-center justify-center rounded bg-slate-50 text-slate-400">
              <Spinner />
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function JobDetailPage(): ReactNode {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { request, requestJson } = useAuth();
  const [job, setJob] = useState<Job | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const inFlight = useRef(false);

  const load = useCallback(
    async (silent = false): Promise<void> => {
      if (inFlight.current) return;
      inFlight.current = true;
      if (!silent) setLoading(true);
      try {
        const [jobData, eventData, artifactData] = await Promise.all([
          requestJson<Job>(`/v1/jobs/${id}`),
          requestJson<JobEvent[]>(`/v1/jobs/${id}/events`),
          requestJson<Artifact[]>(`/v1/jobs/${id}/artifacts`),
        ]);
        setJob(jobData);
        setEvents(eventData);
        setArtifacts(artifactData);
        setError(null);
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "Unable to load the job");
      } finally {
        inFlight.current = false;
        if (!silent) setLoading(false);
      }
    },
    [id, requestJson],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const active = job ? isActiveStatus(job.status) : false;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      void load(true);
    }, 4_000);
    return () => clearInterval(timer);
  }, [active, load]);

  async function cancel(): Promise<void> {
    if (!job) return;
    if (!window.confirm("Cancel this job? The worker stops at the next checkpoint.")) {
      return;
    }
    setCancelling(true);
    setError(null);
    try {
      const response = await request(`/v1/jobs/${job.id}/cancel`, { method: "POST" });
      if (!response.ok) throw await errorFromResponse(response);
      await load(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to cancel the job");
    } finally {
      setCancelling(false);
    }
  }

  async function exportJob(format: "csv" | "json"): Promise<void> {
    if (!job) return;
    setExporting(format);
    setError(null);
    try {
      const response = await request(`/v1/jobs/${job.id}/export?format=${format}`);
      await downloadResponse(response, `job-${job.id}.${format}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Export failed");
    } finally {
      setExporting(null);
    }
  }

  if (loading && !job) {
    return (
      <div className="flex min-h-64 items-center justify-center text-slate-500">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="space-y-4">
        <Link className="text-sm text-slate-600 underline" href="/jobs">
          Back to jobs
        </Link>
        <Alert>{error ?? "Job not found"}</Alert>
      </div>
    );
  }

  const screenshots = artifacts.filter(
    (artifact) =>
      artifact.content_type.startsWith("image/") ||
      artifact.kind === "screenshot" ||
      artifact.kind === "failure_screenshot",
  );
  const otherArtifacts = artifacts.filter((artifact) => !screenshots.includes(artifact));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link className="text-sm text-slate-600 underline" href="/jobs">
            Back to jobs
          </Link>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold text-slate-900">Job detail</h1>
            <Badge tone={statusTone(job.status)}>{job.status}</Badge>
            <Badge>{job.kind}</Badge>
          </div>
          <p className="mt-1 break-all text-sm text-slate-600">{job.url}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {active ? (
            <Button variant="danger" onClick={() => void cancel()} loading={cancelling}>
              Cancel job
            </Button>
          ) : null}
          <Button
            variant="secondary"
            loading={exporting === "json"}
            onClick={() => void exportJob("json")}
          >
            Export JSON
          </Button>
          <Button
            variant="secondary"
            loading={exporting === "csv"}
            onClick={() => void exportJob("csv")}
          >
            Export CSV
          </Button>
          <Button variant="secondary" onClick={() => void load()} loading={loading}>
            Refresh
          </Button>
        </div>
      </div>

      {error ? <Alert>{error}</Alert> : null}

      {job.error ? (
        <Alert>
          <p className="font-medium">
            {job.error.code}: {job.error.message}
          </p>
          {job.error.details ? (
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-xs">
              {prettyJson(job.error.details)}
            </pre>
          ) : null}
        </Alert>
      ) : null}

      <Card>
        <CardHeader title="Run metadata" />
        <dl className="grid grid-cols-1 gap-4 px-5 py-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Job id</dt>
            <dd className="mt-1 break-all font-mono text-xs text-slate-800">{job.id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Attempts</dt>
            <dd className="mt-1 text-slate-800">
              {job.attempts} / {job.max_attempts}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Created</dt>
            <dd className="mt-1 text-slate-800">{formatDate(job.created_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Duration</dt>
            <dd className="mt-1 text-slate-800">{formatDuration(job.duration_ms)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Started</dt>
            <dd className="mt-1 text-slate-800">{formatDate(job.started_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Finished</dt>
            <dd className="mt-1 text-slate-800">{formatDate(job.finished_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">
              Cancel requested
            </dt>
            <dd className="mt-1 text-slate-800">{formatDate(job.cancel_requested_at)}</dd>
          </div>
        </dl>
      </Card>

      <Card>
        <CardHeader
          title="Result"
          description="The extracted payload returned by the worker."
          actions={job.result ? <CopyButton value={prettyJson(job.result)} /> : undefined}
        />
        {job.result ? (
          <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-xs text-slate-800">
            {prettyJson(job.result)}
          </pre>
        ) : (
          <EmptyState
            title="No result yet"
            description={
              active
                ? "The worker is still running this job. The result appears when it finishes."
                : "This job produced no result payload."
            }
          />
        )}
      </Card>

      <Card>
        <CardHeader
          title="Artifacts"
          description="Screenshots and HTML captures, subject to plan retention."
        />
        {artifacts.length === 0 ? (
          <EmptyState
            title="No artifacts"
            description="Request a screenshot or include_html to capture files for this job."
          />
        ) : (
          <div className="space-y-4 px-5 py-4">
            {screenshots.length > 0 ? (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {screenshots.map((artifact) => (
                  <ArtifactCard key={artifact.id} artifact={artifact} request={request} />
                ))}
              </div>
            ) : null}
            {otherArtifacts.map((artifact) => (
              <ArtifactCard key={artifact.id} artifact={artifact} request={request} />
            ))}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Logs and events"
          description="Lifecycle events emitted by the API and worker."
        />
        {events.length === 0 ? (
          <EmptyState
            title="No events"
            description="Events appear as the job is queued, starts, retries, and finishes."
          />
        ) : (
          <ol className="divide-y divide-slate-100">
            {events.map((event) => (
              <li key={event.id} className="px-5 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge>{event.type}</Badge>
                    {event.message ? (
                      <span className="text-sm text-slate-700">{event.message}</span>
                    ) : null}
                  </div>
                  <span className="text-xs text-slate-500">
                    {formatDate(event.created_at)}
                  </span>
                </div>
                {Object.keys(event.data).length > 0 ? (
                  <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-slate-50 p-2 font-mono text-xs text-slate-700">
                    {prettyJson(event.data)}
                  </pre>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
