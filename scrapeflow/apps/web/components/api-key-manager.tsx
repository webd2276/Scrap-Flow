"use client";

import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  CopyButton,
  EmptyState,
  Field,
  Input,
  Spinner,
} from "@/components/ui";
import { ApiError, errorFromResponse } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { ApiKey, ApiKeyCreated } from "@/lib/types";

const SCOPES = [
  "scrape:write",
  "automation:write",
  "jobs:read",
  "schedules:write",
  "exports:read",
  "keys:manage",
  "billing:manage",
  "audit:read",
] as const;

const DEFAULT_SCOPES = [
  "scrape:write",
  "automation:write",
  "jobs:read",
  "schedules:write",
  "exports:read",
];

export function ApiKeyManager(): ReactNode {
  const { request, requestJson } = useAuth();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(DEFAULT_SCOPES);
  const [expiresAt, setExpiresAt] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<ApiKeyCreated | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      setKeys(await requestJson<ApiKey[]>("/v1/keys"));
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to load API keys");
    } finally {
      setLoading(false);
    }
  }, [requestJson]);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleScope(scope: string): void {
    setScopes((current) =>
      current.includes(scope)
        ? current.filter((item) => item !== scope)
        : [...current, scope],
    );
  }

  async function createKey(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setNotice(null);
    if (scopes.length === 0) {
      setError("Select at least one scope");
      return;
    }
    setCreating(true);
    try {
      const response = await request("/v1/keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          scopes,
          expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        }),
      });
      if (!response.ok) throw await errorFromResponse(response);
      setCreatedKey((await response.json()) as ApiKeyCreated);
      setName("");
      setExpiresAt("");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create the key");
    } finally {
      setCreating(false);
    }
  }

  async function revokeKey(key: ApiKey): Promise<void> {
    if (!window.confirm(`Revoke API key "${key.name}"? This cannot be undone.`)) return;
    setRevoking(key.id);
    setError(null);
    setNotice(null);
    try {
      const response = await request(`/v1/keys/${key.id}`, { method: "DELETE" });
      if (!response.ok) throw await errorFromResponse(response);
      setNotice(`Key "${key.name}" revoked.`);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to revoke the key");
    } finally {
      setRevoking(null);
    }
  }

  return (
    <div className="space-y-5">
      {error ? <Alert>{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}

      {createdKey ? (
        <Card>
          <CardHeader
            title="New API key"
            description="Copy it now. The full key is shown once and cannot be recovered."
            actions={<CopyButton value={createdKey.key} label="Copy key" />}
          />
          <div className="space-y-3 px-5 py-4">
            <Alert tone="info">
              Store this key in a secret manager. Anyone with it can use the granted
              scopes until it expires or is revoked.
            </Alert>
            <pre className="overflow-x-auto rounded bg-slate-900 px-4 py-3 font-mono text-xs text-slate-50">
              {createdKey.key}
            </pre>
            <Button variant="secondary" size="sm" onClick={() => setCreatedKey(null)}>
              I have stored it
            </Button>
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Create a key"
          description="Keys are scoped and hashed at rest; only the prefix is stored."
        />
        <form className="space-y-4 px-5 py-4" onSubmit={createKey}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Name">
              <Input
                required
                maxLength={80}
                placeholder="CI pipeline"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </Field>
            <Field label="Expires at" hint="Optional. Leave empty for a non-expiring key.">
              <Input
                type="datetime-local"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
              />
            </Field>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium text-slate-700">Scopes</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {SCOPES.map((scope) => (
                <label
                  key={scope}
                  className="flex items-center gap-2 text-sm text-slate-700"
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-slate-300"
                    checked={scopes.includes(scope)}
                    onChange={() => toggleScope(scope)}
                  />
                  <span className="font-mono text-xs">{scope}</span>
                </label>
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Members can only grant scopes they already hold; owners and admins can grant
              any scope.
            </p>
          </div>
          <Button type="submit" loading={creating}>
            Create key
          </Button>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="API keys"
          description="Use a key as a bearer token against the REST API."
          actions={
            <Button variant="secondary" size="sm" onClick={() => void load()} loading={loading}>
              Refresh
            </Button>
          }
        />
        {loading && !keys ? (
          <div className="flex justify-center px-5 py-12 text-slate-500">
            <Spinner className="h-6 w-6" />
          </div>
        ) : null}
        {!loading && keys && keys.length === 0 ? (
          <EmptyState
            title="No API keys"
            description="Create a key to call the REST API from scripts, CI, or integrations."
          />
        ) : null}
        {keys && keys.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-3 py-3 font-medium">Prefix</th>
                  <th className="px-3 py-3 font-medium">Scopes</th>
                  <th className="px-3 py-3 font-medium">Created</th>
                  <th className="px-3 py-3 font-medium">Last used</th>
                  <th className="px-3 py-3 font-medium">Expires</th>
                  <th className="px-3 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {keys.map((key) => {
                  const revoked = key.revoked_at !== null;
                  return (
                    <tr key={key.id} className={revoked ? "opacity-60" : undefined}>
                      <td className="px-5 py-3 font-medium text-slate-800">{key.name}</td>
                      <td className="px-3 py-3 font-mono text-xs text-slate-600">
                        {key.prefix}…
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex max-w-xs flex-wrap gap-1">
                          {key.scopes.map((scope) => (
                            <Badge key={scope}>{scope}</Badge>
                          ))}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                        {formatDate(key.created_at)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                        {formatDate(key.last_used_at)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                        {formatDate(key.expires_at)}
                      </td>
                      <td className="px-3 py-3">
                        <Badge
                          tone={
                            revoked
                              ? "bg-slate-100 text-slate-700 border-slate-200"
                              : "bg-emerald-100 text-emerald-800 border-emerald-200"
                          }
                        >
                          {revoked ? "revoked" : "active"}
                        </Badge>
                      </td>
                      <td className="px-5 py-3 text-right">
                        {revoked ? null : (
                          <Button
                            variant="danger"
                            size="sm"
                            loading={revoking === key.id}
                            onClick={() => void revokeKey(key)}
                          >
                            Revoke
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
