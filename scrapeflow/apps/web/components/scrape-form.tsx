"use client";

import Link from "next/link";
import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
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
  Select,
} from "@/components/ui";
import { ApiError, errorFromResponse, newIdempotencyKey } from "@/lib/api";
import { prettyJson } from "@/lib/format";
import type { JobAccepted } from "@/lib/types";

export function ScrapeForm(): ReactNode {
  const { request } = useAuth();
  const [url, setUrl] = useState("");
  const [renderJs, setRenderJs] = useState(false);
  const [waitFor, setWaitFor] = useState("");
  const [screenshot, setScreenshot] = useState(false);
  const [includeHtml, setIncludeHtml] = useState(false);
  const [proxyCountry, setProxyCountry] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("");
  const [webhookUrl, setWebhookUrl] = useState("");
  const [selectors, setSelectors] = useState<SelectorRow[]>([newSelectorRow()]);
  const [headers, setHeaders] = useState<KeyValueRow[]>([]);
  const [extract, setExtract] = useState<ExtractOptionsState>(DEFAULT_EXTRACT_OPTIONS);
  const [paginationEnabled, setPaginationEnabled] = useState(false);
  const [paginationMode, setPaginationMode] = useState<"css" | "xpath">("css");
  const [paginationSelector, setPaginationSelector] = useState("");
  const [paginationMaxPages, setPaginationMaxPages] = useState(2);
  const [idempotencyKey, setIdempotencyKey] = useState(() => newIdempotencyKey());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<JobAccepted | null>(null);

  const timeoutValid =
    timeoutSeconds.trim() === "" ||
    (Number(timeoutSeconds) >= 10 && Number(timeoutSeconds) <= 900);
  const countryValid =
    proxyCountry.trim() === "" || /^[A-Za-z]{2}$/.test(proxyCountry.trim());
  const paginationValid = !paginationEnabled || paginationSelector.trim().length > 0;
  const canSubmit =
    url.trim().length > 0 &&
    timeoutValid &&
    countryValid &&
    paginationValid &&
    !(screenshot && !renderJs) &&
    !(waitFor.trim() && !renderJs);

  const payload = useMemo(() => {
    const body: Record<string, unknown> = {
      url: url.trim(),
      render_js: renderJs,
      selectors: rowsToSelectors(selectors),
      extract: extractOptionsPayload(extract),
      screenshot,
      include_html: includeHtml,
      headers: rowsToRecord(headers),
    };
    if (renderJs && waitFor.trim()) body.wait_for = waitFor.trim();
    if (proxyCountry.trim()) body.proxy_country = proxyCountry.trim().toUpperCase();
    if (timeoutSeconds.trim()) body.timeout_seconds = Number(timeoutSeconds);
    if (webhookUrl.trim()) body.webhook_url = webhookUrl.trim();
    if (paginationEnabled) {
      body.pagination = {
        next_selector: { [paginationMode]: paginationSelector.trim(), attr: "href" },
        max_pages: paginationMaxPages,
      };
    }
    return body;
  }, [
    extract,
    headers,
    includeHtml,
    paginationEnabled,
    paginationMaxPages,
    paginationMode,
    paginationSelector,
    proxyCountry,
    renderJs,
    screenshot,
    selectors,
    timeoutSeconds,
    url,
    waitFor,
    webhookUrl,
  ]);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setAccepted(null);
    setSubmitting(true);
    try {
      const response = await request("/v1/scrape", {
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
      setError(caught instanceof ApiError ? caught.message : "Unable to submit the scrape");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]" onSubmit={onSubmit}>
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
            description="Use only sites you own or are authorised to access."
          />
          <div className="space-y-4 px-5 py-4">
            <Field label="URL" hint="Absolute http(s) URL.">
              <Input
                type="url"
                required
                placeholder="https://example.com/pricing"
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
                  checked={renderJs}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setRenderJs(checked);
                    if (!checked) {
                      setScreenshot(false);
                      setWaitFor("");
                    }
                  }}
                />
                Render with a real browser
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
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  className="h-4 w-4 rounded border-slate-300"
                  disabled={!renderJs}
                  checked={screenshot}
                  onChange={(event) => setScreenshot(event.target.checked)}
                />
                Capture a screenshot
              </label>
              <Field label="Wait for selector" hint="Browser jobs only.">
                <Input
                  disabled={!renderJs}
                  placeholder=".results"
                  value={waitFor}
                  onChange={(event) => setWaitFor(event.target.value)}
                />
              </Field>
            </div>
            {!renderJs && (screenshot || waitFor.trim()) ? (
              <p className="text-xs text-rose-700">
                Screenshots and wait-for require browser rendering.
              </p>
            ) : null}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Selectors"
            description="Named CSS or XPath queries returned in the result."
          />
          <div className="px-5 py-4">
            <SelectorEditor rows={selectors} onChange={setSelectors} />
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Extraction"
            description="Choose the page-level data returned alongside selectors."
          />
          <div className="px-5 py-4">
            <ExtractOptionsEditor value={extract} onChange={setExtract} />
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Pagination"
            description="Follow a next-page selector and merge each page."
          />
          <div className="space-y-3 px-5 py-4">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300"
                checked={paginationEnabled}
                onChange={(event) => setPaginationEnabled(event.target.checked)}
              />
              Enable pagination
            </label>
            {paginationEnabled ? (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-[8rem_minmax(0,1fr)_8rem]">
                <Select
                  aria-label="Next selector type"
                  value={paginationMode}
                  onChange={(event) =>
                    setPaginationMode(event.target.value as "css" | "xpath")
                  }
                >
                  <option value="css">CSS</option>
                  <option value="xpath">XPath</option>
                </Select>
                <Input
                  aria-label="Next page selector"
                  placeholder="a.next"
                  value={paginationSelector}
                  onChange={(event) => setPaginationSelector(event.target.value)}
                />
                <Input
                  aria-label="Maximum pages"
                  type="number"
                  min={2}
                  max={500}
                  value={paginationMaxPages}
                  onChange={(event) =>
                    setPaginationMaxPages(
                      Math.min(500, Math.max(2, Number(event.target.value) || 2)),
                    )
                  }
                />
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Request headers"
            description="At most 20 headers; hop-by-hop headers are rejected."
          />
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
                Queue scrape
              </Button>
              <span className="text-xs text-slate-500">
                Credits are reserved when the job is accepted.
              </span>
            </div>
          </div>
        </Card>
      </div>

      <div className="lg:sticky lg:top-6 lg:self-start">
        <Card>
          <CardHeader
            title="Live request preview"
            description="Exactly what will be sent to POST /v1/scrape."
            actions={<Badge>{Object.keys(rowsToSelectors(selectors)).length} selectors</Badge>}
          />
          <pre className="max-h-[40rem] overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-xs text-slate-800">
            {prettyJson(payload)}
          </pre>
        </Card>
      </div>
    </form>
  );
}
