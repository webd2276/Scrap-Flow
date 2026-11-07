"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { ApiError, errorFromResponse } from "@/lib/api";
import { downloadResponse } from "@/lib/download";
import { formatDate, statusTone } from "@/lib/format";
import type {
  JobKind,
  Schedule,
  ScheduleList,
  ScheduleRun,
  ScheduleRunList,
} from "@/lib/types";

const DEFAULT_TEMPLATES: Record<JobKind, string> = {
  scrape: JSON.stringify(
    {
      url: "https://example.com",
      render_js: false,
      selectors: {},
    },
    null,
    2,
  ),
  automation: JSON.stringify(
    {
      url: "https://example.com",
      steps: [{ action: "goto", url: "https://example.com" }],
    },
    null,
    2,
  ),
};

function parseWatchedFields(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function parseTemplate(value: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("Template must be valid JSON");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("Template must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

interface EditState {
  id: string;
  name: string;
  cron: string;
  timezone: string;
  templateText: string;
  watchedFields: string;
  notifyOnChange: boolean;
  enabled: boolean;
}

export function ScheduleManager(): ReactNode {
  const { request, requestJson } = useAuth();
  const [data, setData] = useState<ScheduleList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [kind, setKind] = useState<JobKind>("scrape");
  const [cron, setCron] = useState("0 * * * *");
  const [timezone, setTimezone] = useState("UTC");
  const [templateText, setTemplateText] = useState(DEFAULT_TEMPLATES.scrape);
  const [watchedFields, setWatchedFields] = useState("");
  const [notifyOnChange, setNotifyOnChange] = useState(true);
  const [enabled, setEnabled] = useState(true);
  const [creating, setCreating] = useState(false);

  const [edit, setEdit] = useState<EditState | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [history, setHistory] = useState<ScheduleRun[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const load = useCallback(
    async (silent = false): Promise<void> => {
      if (!silent) setLoading(true);
      try {
        const result = await requestJson<ScheduleList>("/v1/schedules?limit=100");
        setData(result);
        setError(null);
      } catch (caught) {
        setError(
          caught instanceof ApiError ? caught.message : "Unable to load schedules",
        );
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [requestJson],
  );

  useEffect(() => {
    void load();
  }, [load]);

  async function createSchedule(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setNotice(null);
    let template: Record<string, unknown>;
    try {
      template = parseTemplate(templateText);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid template");
      return;
    }
    setCreating(true);
    try {
      const response = await request("/v1/schedules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          kind,
          cron,
          timezone,
          enabled,
          template,
          watched_fields: parseWatchedFields(watchedFields),
          notify_on_change: notifyOnChange,
        }),
      });
      if (!response.ok) throw await errorFromResponse(response);
      setNotice("Schedule created.");
      setName("");
      setWatchedFields("");
      await load(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Unable to create the schedule",
      );
    } finally {
      setCreating(false);
    }
  }

  async function patchSchedule(
    id: string,
    body: Record<string, unknown>,
    successMessage: string,
  ): Promise<void> {
    setBusy(id);
    setError(null);
    setNotice(null);
    try {
      const response = await request(`/v1/schedules/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw await errorFromResponse(response);
      setNotice(successMessage);
      await load(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to update the schedule");
    } finally {
      setBusy(null);
    }
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!edit) return;
    setError(null);
    setNotice(null);
    let template: Record<string, unknown>;
    try {
      template = parseTemplate(edit.templateText);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Invalid template");
      return;
    }
    setSavingEdit(true);
    try {
      const response = await request(`/v1/schedules/${edit.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: edit.name,
          cron: edit.cron,
          timezone: edit.timezone,
          enabled: edit.enabled,
          template,
          watched_fields: parseWatchedFields(edit.watchedFields),
          notify_on_change: edit.notifyOnChange,
        }),
      });
      if (!response.ok) throw await errorFromResponse(response);
      setNotice("Schedule updated.");
      setEdit(null);
      await load(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to update the schedule");
    } finally {
      setSavingEdit(false);
    }
  }

  async function runNow(schedule: Schedule): Promise<void> {
    setBusy(schedule.id);
    setError(null);
    setNotice(null);
    try {
      const response = await request(`/v1/schedules/${schedule.id}/run`, {
        method: "POST",
      });
      if (!response.ok) throw await errorFromResponse(response);
      setNotice(`Schedule "${schedule.name}" dispatched.`);
      await load(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to run the schedule");
    } finally {
      setBusy(null);
    }
  }

  async function remove(schedule: Schedule): Promise<void> {
    if (!window.confirm(`Delete schedule "${schedule.name}"? Run history is kept.`)) {
      return;
    }
    setBusy(schedule.id);
    setError(null);
    setNotice(null);
    try {
      const response = await request(`/v1/schedules/${schedule.id}`, {
        method: "DELETE",
      });
      if (!response.ok) throw await errorFromResponse(response);
      setNotice("Schedule deleted.");
      if (historyFor === schedule.id) setHistoryFor(null);
      await load(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to delete the schedule");
    } finally {
      setBusy(null);
    }
  }

  async function toggleHistory(schedule: Schedule): Promise<void> {
    if (historyFor === schedule.id) {
      setHistoryFor(null);
      return;
    }
    setHistoryFor(schedule.id);
    setHistory([]);
    setHistoryLoading(true);
    setError(null);
    try {
      const result = await requestJson<ScheduleRunList>(
        `/v1/schedules/${schedule.id}/runs?limit=25`,
      );
      setHistory(result.items);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to load run history");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function exportHistory(schedule: Schedule, format: "csv" | "json"): Promise<void> {
    setBusy(schedule.id);
    setError(null);
    try {
      const response = await request(
        `/v1/schedules/${schedule.id}/export?format=${format}`,
      );
      await downloadResponse(response, `schedule-${schedule.id}.${format}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Export failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      {error ? <Alert>{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}

      <Card>
        <CardHeader
          title="Create a schedule"
          description="Cron expressions use five fields. Templates are validated with the same schema as ad-hoc jobs."
        />
        <form className="space-y-4 px-5 py-4" onSubmit={createSchedule}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name">
              <Input
                required
                minLength={1}
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <Field label="Job kind">
              <Select
                value={kind}
                onChange={(event) => {
                  const next = event.target.value as JobKind;
                  setKind(next);
                  setTemplateText(DEFAULT_TEMPLATES[next]);
                }}
              >
                <option value="scrape">Scrape</option>
                <option value="automation">Automation</option>
              </Select>
            </Field>
            <Field label="Cron" hint="For example */15 * * * * or 0 9 * * 1-5.">
              <Input
                required
                value={cron}
                onChange={(event) => setCron(event.target.value)}
              />
            </Field>
            <Field label="Timezone" hint="IANA name, for example Europe/Berlin.">
              <Input
                required
                value={timezone}
                onChange={(event) => setTimezone(event.target.value)}
              />
            </Field>
          </div>
          <Field
            label="Job template"
            hint="Scrape: url, render_js, selectors, extract. Automation: url and steps; secrets and webhook_url are not allowed."
          >
            <Textarea
              rows={10}
              value={templateText}
              onChange={(event) => setTemplateText(event.target.value)}
            />
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field
              label="Watched fields"
              hint="Comma-separated result paths such as result.price, title, pages[0].text."
            >
              <Input
                value={watchedFields}
                onChange={(event) => setWatchedFields(event.target.value)}
              />
            </Field>
            <div className="space-y-2 pt-6">
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300"
                  checked={notifyOnChange}
                  onChange={(event) => setNotifyOnChange(event.target.checked)}
                />
                Notify on watched-field changes
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300"
                  checked={enabled}
                  onChange={(event) => setEnabled(event.target.checked)}
                />
                Enabled
              </label>
            </div>
          </div>
          <Button type="submit" loading={creating}>
            Create schedule
          </Button>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="Schedules"
          description="Recurring jobs for this organisation."
          actions={
            <Button variant="secondary" size="sm" onClick={() => void load()} loading={loading}>
              Refresh
            </Button>
          }
        />
        {loading && !data ? (
          <div className="flex justify-center px-5 py-12 text-slate-500">
            <Spinner className="h-6 w-6" />
          </div>
        ) : null}
        {!loading && data && data.items.length === 0 ? (
          <EmptyState
            title="No schedules"
            description="Create a cron schedule above to run a scrape or automation repeatedly."
          />
        ) : null}
        <div className="divide-y divide-slate-100">
          {data?.items.map((schedule) => (
            <div key={schedule.id} className="px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-semibold text-slate-900">
                      {schedule.name}
                    </h3>
                    <Badge>{schedule.kind}</Badge>
                    <Badge tone={schedule.enabled ? statusTone("succeeded") : statusTone("cancelled")}>
                      {schedule.enabled ? "enabled" : "disabled"}
                    </Badge>
                  </div>
                  <p className="mt-1 font-mono text-xs text-slate-600">
                    {schedule.cron} · {schedule.timezone}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Next run {formatDate(schedule.next_run_at)} · Last run{" "}
                    {formatDate(schedule.last_run_at)}
                  </p>
                  {schedule.watched_fields.length > 0 ? (
                    <p className="mt-1 text-xs text-slate-500">
                      Watching {schedule.watched_fields.join(", ")}
                    </p>
                  ) : null}
                  {schedule.last_error ? (
                    <p className="mt-1 text-xs text-rose-700">{schedule.last_error}</p>
                  ) : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setEdit({
                        id: schedule.id,
                        name: schedule.name,
                        cron: schedule.cron,
                        timezone: schedule.timezone,
                        templateText: JSON.stringify(schedule.template, null, 2),
                        watchedFields: schedule.watched_fields.join(", "),
                        notifyOnChange: schedule.notify_on_change,
                        enabled: schedule.enabled,
                      });
                    }}
                  >
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    loading={busy === schedule.id}
                    onClick={() => void runNow(schedule)}
                  >
                    Run now
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() =>
                      void patchSchedule(
                        schedule.id,
                        { enabled: !schedule.enabled },
                        schedule.enabled ? "Schedule disabled." : "Schedule enabled.",
                      )
                    }
                  >
                    {schedule.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void toggleHistory(schedule)}
                  >
                    {historyFor === schedule.id ? "Hide history" : "History"}
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void exportHistory(schedule, "csv")}
                  >
                    CSV
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => void exportHistory(schedule, "json")}
                  >
                    JSON
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => void remove(schedule)}>
                    Delete
                  </Button>
                </div>
              </div>

              {schedule.last_job_id ? (
                <p className="mt-2 text-xs text-slate-500">
                  Last job:{" "}
                  <Link
                    className="underline"
                    href={`/jobs/${schedule.last_job_id}`}
                  >
                    {schedule.last_job_id}
                  </Link>
                </p>
              ) : null}

              {edit?.id === schedule.id ? (
                <form
                  className="mt-4 space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4"
                  onSubmit={saveEdit}
                >
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <Field label="Name">
                      <Input
                        required
                        value={edit.name}
                        onChange={(event) =>
                          setEdit({ ...edit, name: event.target.value })
                        }
                      />
                    </Field>
                    <Field label="Cron">
                      <Input
                        required
                        value={edit.cron}
                        onChange={(event) =>
                          setEdit({ ...edit, cron: event.target.value })
                        }
                      />
                    </Field>
                    <Field label="Timezone">
                      <Input
                        required
                        value={edit.timezone}
                        onChange={(event) =>
                          setEdit({ ...edit, timezone: event.target.value })
                        }
                      />
                    </Field>
                  </div>
                  <Field label="Job template">
                    <Textarea
                      rows={10}
                      value={edit.templateText}
                      onChange={(event) =>
                        setEdit({ ...edit, templateText: event.target.value })
                      }
                    />
                  </Field>
                  <Field label="Watched fields">
                    <Input
                      value={edit.watchedFields}
                      onChange={(event) =>
                        setEdit({ ...edit, watchedFields: event.target.value })
                      }
                    />
                  </Field>
                  <div className="flex flex-wrap gap-4 text-sm text-slate-700">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-slate-300"
                        checked={edit.notifyOnChange}
                        onChange={(event) =>
                          setEdit({ ...edit, notifyOnChange: event.target.checked })
                        }
                      />
                      Notify on change
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-slate-300"
                        checked={edit.enabled}
                        onChange={(event) =>
                          setEdit({ ...edit, enabled: event.target.checked })
                        }
                      />
                      Enabled
                    </label>
                  </div>
                  <div className="flex gap-2">
                    <Button type="submit" size="sm" loading={savingEdit}>
                      Save changes
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => setEdit(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              ) : null}

              {historyFor === schedule.id ? (
                <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200">
                  {historyLoading ? (
                    <div className="flex justify-center py-6 text-slate-500">
                      <Spinner />
                    </div>
                  ) : history.length === 0 ? (
                    <p className="px-4 py-4 text-sm text-slate-500">No runs yet.</p>
                  ) : (
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                      <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                        <tr>
                          <th className="px-3 py-2 font-medium">Status</th>
                          <th className="px-3 py-2 font-medium">Trigger</th>
                          <th className="px-3 py-2 font-medium">Scheduled for</th>
                          <th className="px-3 py-2 font-medium">Credits</th>
                          <th className="px-3 py-2 font-medium">Job</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {history.map((run) => (
                          <tr key={run.id}>
                            <td className="px-3 py-2">
                              <Badge tone={statusTone(run.status)}>{run.status}</Badge>
                            </td>
                            <td className="px-3 py-2 text-slate-600">{run.trigger}</td>
                            <td className="px-3 py-2 text-slate-600">
                              {formatDate(run.scheduled_for)}
                            </td>
                            <td className="px-3 py-2 text-slate-600">{run.credits}</td>
                            <td className="px-3 py-2">
                              {run.job_id ? (
                                <Link className="underline" href={`/jobs/${run.job_id}`}>
                                  Open
                                </Link>
                              ) : (
                                <span className="text-slate-400">—</span>
                              )}
                              {run.error ? (
                                <p className="text-xs text-rose-700">{run.error}</p>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
