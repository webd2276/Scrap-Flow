"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { ApiError } from "@/lib/api";

export default function LoginPage(): ReactNode {
  const { status, login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgSlug, setOrgSlug] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace("/jobs");
  }, [status, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email, password, orgSlug: orgSlug.trim() || undefined });
      router.replace("/jobs");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to sign in");
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
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">Sign in</h1>
          <p className="mt-1 text-sm text-slate-500">
            Run scrapes, automation, schedules, and exports from one place.
          </p>
        </div>

        <Card className="p-6">
          <form className="space-y-4" onSubmit={onSubmit}>
            {error ? <Alert>{error}</Alert> : null}
            <Field label="Email">
              <Input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            <Field label="Organisation slug" hint="Only needed when one account belongs to several organisations.">
              <Input
                value={orgSlug}
                onChange={(event) => setOrgSlug(event.target.value)}
                placeholder="optional"
              />
            </Field>
            <Button type="submit" className="w-full" loading={submitting}>
              Sign in
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center text-sm text-slate-600">
          No account?{" "}
          <Link className="font-medium text-slate-900 underline" href="/signup">
            Create an organisation
          </Link>
        </p>
      </div>
    </main>
  );
}
