"use client";

import Link from "next/link";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { StepEditor } from "@/components/automation-step-editor";
import {
  DEFAULT_EXTRACT_OPTIONS,
  ExtractOptionsEditor,
  extractOptionsPayload,
  type ExtractOptionsState,
} from "@/components/extract-options";
import {
  KeyValueEditor,
  rowsToRecord,
  type KeyValueRow,
} from "@/components/key-value-editor";
import {
  SelectorEditor,
  newSelectorRow,
  rowsToSelectors,
  type SelectorRow,
} from "@/components/selector-editor";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  Field,
  Input,
} from "@/components/ui";
import { ApiError, errorFromResponse, newIdempotencyKey } from "@/lib/api";
import {
  buildAutomationPayload,
  countSteps,
  missingSecret,
  newStep,
  validateSteps,
} from "@/lib/automation";
import { prettyJson } from "@/lib/format";
import type { JobAccepted } from "@/lib/types";

export function AutomationBuilder(): ReactNode {
  const { request } = useAuth();
  const [url, setUrl] = useState("");
  const [proxyCountry, setProxyCountry] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [screenshot, setScreenshot] = useState(false);
  const [includeHtml, setIncludeHtml] = useState(false);
  const [steps, setSteps] = useState(() => [newStep("goto")]);
  const [secrets, setSecrets] = useState<KeyValueRow[]>([]);
  const [headers, setHeaders] = useState<KeyValueRow[]>([]);
  const [selectors, setSelectors] = useState<SelectorRow[]>([newSelectorRow()]);
  const [extract, setExtract] = useState<ExtractOptionsState>(DEFAULT_EXTRACT_OPTIONS);
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<JobAccepted | null>(null);

  const timeoutValid =
    timeoutSeconds.trim() === "" ||
    (Number(timeoutSeconds) >= 10 && Number(timeoutSeconds) <= 900);
  const countryValid =
    proxyCountry.trim() === "" || /^[A-Za-z]{2}$/.test(proxyCountry.trim());
  const urlValid = /^https?:\/\/\S+$/i.test(url.trim());
  const stepError = validateSteps(steps);
  const secretNames = new Set(
    secrets.map((row) => row.name.trim()).filter((name) => name.length > 0),
  );
  const secretError = missingSecret(steps, secretNames);
  const canSubmit =
    urlValid && !stepError && !secretError && timeoutValid && countryValid;

  const payload = useMemo(
    () =>
      buildAutomationPayload({
        url,
        steps,
        secrets: rowsToRecord(secrets),
        selectors: rowsToSelectors(selectors),
        extract: extractOptionsPayload(extract),
        screenshot,
        includeHtml,
        proxyCountry,
        timeout: timeoutSeconds,
        webhookUrl,
        headers: rowsToRecord(headers),
      }),
    [
      extract,
      headers,
      includeHtml,
      proxyCountry,
      screenshot,
      secrets,
      selectors,
      steps,
      timeoutSeconds,
      url,
      webhookUrl,
    ],
  );

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setAccepted(null);
    if (stepError) {
      setError(stepError);
      return;
    }
    if (secretError) {
      setError(secretError);
      return;
    }
    setSubmitting(true);
    try {
      const response = await request("/v1/automate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw await errorFromResponse(response);
      setAccepted((await response.json()) as JobAccepted);
      setIdempotencyKey(newIdempotencyKey());
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Unable to submit the automation",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
      onSubmit={onSubmit}
    >
      <div className="space-y-5">
        {error ? <Alert>{error}</Alert> : null}
        {accepted ? (
          <Alert tone="success">
            Job {accepted.job.status}
            {accepted.deduplicated ? " (idempotent replay)" : ""}.{" "}
            <Link className="font-medium underline" href={`/jobs/${accepted.job.id}`}>
              Open job detail
            </Link>
          </Alert>
        ) : null}

        <Card>
          <CardHeader
            title="Target"
            description="The workflow starts at this URL and runs in a real browser."
          />
          <div className="space-y-4 px-5 py-4">
            <Field label="URL">
              <Input
                type="url"
                required
                placeholder="https://example.com/login"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
              />
            </Field>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Proxy country" hint="Optional ISO country; requires a configured provider.">
                <Input
                  maxLength={2}
                  placeholder="DE"
                  value={proxyCountry}
                  onChange={(event) => setProxyCountry(event.target.value)}
                />
              </Field>
              <Field label="Timeout" hint="Seconds, 10–900. Defaults to the server limit.">
                <Input
                  type="number"
                  min={10}
                  max={900}
                  placeholder="default"
                  value={timeoutSeconds}
                  onChange={(event) => setTimeoutSeconds(event.target.value)}
                />
              </Field>
            </div>
            <Field label="Webhook URL" hint="Optional HTTPS endpoint notified on completion.">
              <Input
                type="url"
                placeholder="https://hooks.example.com/scrapeflow"
                value={webhookUrl}
                onChange={(event) => setWebhookUrl(event.target.value)}
              />
            </Field>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300"
                  checked={screenshot}
                  onChange={(event) => setScreenshot(event.target.checked)}
                />
                Capture the final page
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300"
                  checked={includeHtml}
                  onChange={(event) => setIncludeHtml(event.target.checked)}
                />
                Include page HTML artifact
              </label>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Steps"
            description="Steps run in order. Retries only re-run before a mutating step succeeds."
            actions={<Badge>{countSteps(steps)} steps</Badge>}
          />
          <div className="space-y-3 px-5 py-4">
            {steps.map((step, index) => (
              <StepEditor
                key={step.id}
                step={step}
                depth={1}
                index={index}
                onChange={(next) =>
                  setSteps((current) =>
                    current.map((item) => (item.id === next.id ? next : item)),
                  )
                }
                onRemove={() =>
                  setSteps((current) => current.filter((item) => item.id !== step.id))
                }
              />
            ))}
            {steps.length === 0 ? (
              <p className="text-sm text-rose-700">Add at least one step.</p>
            ) : null}
            {stepError && steps.length > 0 ? (
              <p className="text-sm text-rose-700">{stepError}</p>
            ) : null}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setSteps((current) => [...current, newStep("click")])}
            >
              Add step
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Secrets"
            description="Use {{name}} in type, select, and press steps. Values are never stored in the job payload or result."
          />
          <div className="space-y-2 px-5 py-4">
            <KeyValueEditor
              rows={secrets}
              onChange={setSecrets}
              namePlaceholder="secret name"
              valuePlaceholder="secret value"
              secret
              addLabel="Add secret"
            />
            {secretError ? <p className="text-sm text-rose-700">{secretError}</p> : null}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Additional selectors"
            description="Named CSS or XPath queries merged into the result."
          />
          <div className="px-5 py-4">
            <SelectorEditor rows={selectors} onChange={setSelectors} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Extraction" description="Page-level data returned with the step output." />
          <div className="px-5 py-4">
            <ExtractOptionsEditor value={extract} onChange={setExtract} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Request headers" description="At most 20 headers." />
          <div className="px-5 py-4">
            <KeyValueEditor
              rows={headers}
              onChange={setHeaders}
              namePlaceholder="Header name"
              valuePlaceholder="Header value"
              addLabel="Add header"
            />
          </div>
        </Card>

        <Card>
          <CardHeader title="Submission" description="The key deduplicates retries for 24 hours." />
          <div className="space-y-3 px-5 py-4">
            <Field label="Idempotency key">
              <div className="flex gap-2">
                <Input
                  value={idempotencyKey}
                  readOnly
                  className="font-mono text-xs"
                  aria-label="Idempotency key"
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setIdempotencyKey(newIdempotencyKey())}
                >
                  New key
                </Button>
              </div>
            </Field>
            <div className="flex items-center gap-3">
              <Button type="submit" loading={submitting} disabled={!canSubmit}>
                Queue automation
              </Button>
              <span className="text-xs text-slate-500">
                {urlValid ? "Ready when the steps are valid." : "Enter an absolute http(s) URL."}
              </span>
            </div>
          </div>
        </Card>
      </div>

      <div className="lg:sticky lg:top-6 lg:self-start">
        <Card>
          <CardHeader
            title="Live request preview"
            description="Exactly what will be sent to POST /v1/automate."
          />
          <pre className="max-h-[40rem] overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-xs text-slate-800">
            {prettyJson(payload)}
          </pre>
        </Card>
      </div>
    </form>
  );
}
