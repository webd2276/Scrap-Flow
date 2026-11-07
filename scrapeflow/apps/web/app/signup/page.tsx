"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";

export default function SignupPage(): ReactNode {
  const { status, signup } = useAuth();
  const router = useRouter();
  const [orgName, setOrgName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace("/jobs");
  }, [status, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    if (!accepted) {
      setError("Accept the Terms of Service and acceptable-use policy to continue");
      return;
    }
    setSubmitting(true);
    try {
      await signup({ orgName, email, password, displayName });
      router.replace("/jobs");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create the account");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <p className="text-sm font-semibold uppercase tracking-widest text-slate-500">
            ScrapeFlow
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">Create your organisation</h1>
          <p className="mt-1 text-sm text-slate-500">
            Start with the free plan. Upgrade from the billing page when you need more.
          </p>
        </div>

        <Card className="p-6">
          <form className="space-y-4" onSubmit={onSubmit}>
            {error ? <Alert>{error}</Alert> : null}
            <Field label="Organisation name">
              <Input
                required
                minLength={2}
                maxLength={120}
                value={orgName}
                onChange={(event) => setOrgName(event.target.value)}
              />
            </Field>
            <Field label="Your name">
              <Input
                maxLength={120}
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
            </Field>
            <Field label="Email">
              <Input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
            <Field label="Password" hint="At least 12 characters.">
              <Input
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 rounded border-slate-300"
                checked={accepted}
                onChange={(event) => setAccepted(event.target.checked)}
              />
              <span>
                I accept the{" "}
                <Link className="underline" href="/terms">
                  Terms of Service and acceptable-use policy
                </Link>
                .
              </span>
            </label>
            <Button type="submit" className="w-full" loading={submitting}>
              Create account
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center text-sm text-slate-600">
          Already have an account?{" "}
          <Link className="font-medium text-slate-900 underline" href="/login">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
