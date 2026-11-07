"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Spinner,
} from "@/components/ui";
import { ApiError, errorFromResponse, isSafeHttpsUrl } from "@/lib/api";
import { formatReset } from "@/lib/format";
import type { Plan, Usage } from "@/lib/types";

export function BillingPanel(): ReactNode {
  const { request, requestJson } = useAuth();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [checkoutPlan, setCheckoutPlan] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      const [usageResult, planResult] = await Promise.all([
        requestJson<Usage>("/v1/billing/usage"),
        requestJson<Plan[]>("/v1/billing/plans"),
      ]);
      setUsage(usageResult);
      setPlans(planResult);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to load billing");
    } finally {
      setLoading(false);
    }
  }, [requestJson]);

  useEffect(() => {
    void load();
  }, [load]);

  async function startCheckout(plan: string): Promise<void> {
    setCheckoutPlan(plan);
    setError(null);
    setNotice(null);
    try {
      const response = await request("/v1/billing/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          plan,
          success_url: `${window.location.origin}/billing`,
          cancel_url: `${window.location.origin}/billing`,
        }),
      });
      if (!response.ok) throw await errorFromResponse(response);
      const payload = (await response.json()) as { url: string };
      if (!isSafeHttpsUrl(payload.url)) {
        throw new ApiError(502, "UPSTREAM_ERROR", "Billing returned an unsafe redirect");
      }
      window.location.assign(payload.url);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Unable to start checkout",
      );
      setCheckoutPlan(null);
    }
  }

  async function openPortal(): Promise<void> {
    setPortalLoading(true);
    setError(null);
    setNotice(null);
    try {
      const response = await request("/v1/billing/portal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ return_url: `${window.location.origin}/billing` }),
      });
      if (!response.ok) throw await errorFromResponse(response);
      const payload = (await response.json()) as { url: string };
      if (!isSafeHttpsUrl(payload.url)) {
        throw new ApiError(502, "UPSTREAM_ERROR", "Billing returned an unsafe redirect");
      }
      window.location.assign(payload.url);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Unable to open the billing portal",
      );
      setPortalLoading(false);
    }
  }

  if (loading && !usage) {
    return (
      <div className="flex min-h-64 items-center justify-center text-slate-500">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!usage) {
    return <Alert>{error ?? "Billing is unavailable"}</Alert>;
  }

  const percent =
    usage.monthly_credits > 0
      ? Math.min(100, Math.round((usage.used / usage.monthly_credits) * 100))
      : 0;
  const paid = usage.billing_enabled;

  return (
    <div className="space-y-5">
      {error ? <Alert>{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      {!paid ? (
        <Alert tone="info">
          Stripe billing is not configured on this deployment. Usage and plan limits are
          enforced, but upgrades and the customer portal are unavailable.
        </Alert>
      ) : null}

      <Card>
        <CardHeader
          title="Current usage"
          description={`${usage.plan_name} plan · ${usage.period}`}
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void load()}
              loading={loading}
            >
              Refresh
            </Button>
          }
        />
        <div className="space-y-4 px-5 py-4">
          <div>
            <div className="flex flex-wrap items-end justify-between gap-2">
              <p className="text-2xl font-semibold text-slate-900">
                {usage.used.toLocaleString()}
                <span className="ml-1 text-sm font-normal text-slate-500">
                  / {usage.monthly_credits.toLocaleString()} credits
                </span>
              </p>
              <p className="text-sm text-slate-600">
                {usage.remaining.toLocaleString()} remaining · resets in{" "}
                {formatReset(usage.reset_seconds)}
              </p>
            </div>
            <div
              className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-200"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={usage.monthly_credits}
              aria-valuenow={usage.used}
            >
              <div
                className={`h-full rounded-full ${
                  percent >= 90 ? "bg-rose-500" : percent >= 70 ? "bg-amber-500" : "bg-slate-900"
                }`}
                style={{ width: `${percent}%` }}
              />
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Concurrency
              </dt>
              <dd className="mt-1 text-slate-800">{usage.max_concurrency}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Max steps
              </dt>
              <dd className="mt-1 text-slate-800">{usage.max_steps}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Max pages
              </dt>
              <dd className="mt-1 text-slate-800">{usage.max_pages}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">
                Artifact retention
              </dt>
              <dd className="mt-1 text-slate-800">
                {usage.artifact_retention_days} days
              </dd>
            </div>
          </dl>
          <div>
            <Button
              variant="secondary"
              size="sm"
              disabled={!paid}
              loading={portalLoading}
              onClick={() => void openPortal()}
            >
              Manage subscription
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Plans"
          description="Upgrades take effect after Stripe confirms the subscription."
        />
        {!plans || plans.length === 0 ? (
          <EmptyState
            title="No plans available"
            description="The plan catalog could not be loaded."
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 px-5 py-4 md:grid-cols-2 xl:grid-cols-4">
            {plans.map((plan) => {
              const current = plan.code === usage.plan;
              return (
                <div
                  key={plan.code}
                  className={`flex flex-col rounded-lg border p-4 ${
                    current ? "border-slate-900 bg-slate-50" : "border-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold text-slate-900">{plan.name}</h3>
                    {current ? <Badge>current</Badge> : null}
                  </div>
                  <p className="mt-2 text-2xl font-semibold text-slate-900">
                    {plan.monthly_credits.toLocaleString()}
                    <span className="ml-1 text-xs font-normal text-slate-500">
                      credits / month
                    </span>
                  </p>
                  <ul className="mt-3 flex-1 space-y-1 text-xs text-slate-600">
                    <li>{plan.max_concurrency} concurrent jobs</li>
                    <li>{plan.max_steps} automation steps</li>
                    <li>{plan.max_pages} pages per scrape</li>
                    <li>{plan.artifact_retention_days}-day artifacts</li>
                  </ul>
                  <div className="mt-4">
                    {current ? (
                      <Button variant="secondary" size="sm" disabled className="w-full">
                        Current plan
                      </Button>
                    ) : plan.code === "free" ? (
                      <Button variant="secondary" size="sm" disabled className="w-full">
                        Downgrade in portal
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        className="w-full"
                        disabled={!paid}
                        loading={checkoutPlan === plan.code}
                        onClick={() => void startCheckout(plan.code)}
                      >
                        Upgrade
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
