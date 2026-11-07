"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { Badge, Button, Spinner } from "@/components/ui";

const NAV = [
  { href: "/jobs", label: "Jobs" },
  { href: "/scrape", label: "Scrape" },
  { href: "/automate", label: "Automate" },
  { href: "/schedules", label: "Schedules" },
  { href: "/keys", label: "API keys" },
  { href: "/billing", label: "Billing" },
];

export function DashboardShell({ children }: { children: ReactNode }): ReactNode {
  const { status, me, orgId, role, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  const org = useMemo(
    () => me?.orgs.find((item) => item.id === orgId) ?? me?.orgs[0] ?? null,
    [me, orgId],
  );

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-500">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (status === "anonymous") {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">
        Redirecting to sign in…
      </div>
    );
  }

  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-60 shrink-0 border-r border-slate-200 bg-white lg:flex lg:flex-col">
        <div className="border-b border-slate-100 px-5 py-5">
          <Link href="/jobs" className="text-lg font-semibold tracking-tight">
            ScrapeFlow
          </Link>
          <p className="mt-1 truncate text-xs text-slate-500">{org?.name ?? "Organisation"}</p>
        </div>
        <nav className="flex-1 space-y-1 px-3 py-4">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`block rounded-md px-3 py-2 text-sm font-medium ${
                  active
                    ? "bg-slate-900 text-white"
                    : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-slate-100 px-4 py-4">
          <p className="truncate text-sm font-medium text-slate-800">
            {me?.display_name || me?.email}
          </p>
          <p className="truncate text-xs text-slate-500">{me?.email}</p>
          <div className="mt-2 flex items-center gap-2">
            <Badge>{org?.plan ?? "free"}</Badge>
            <Badge>{role ?? org?.role ?? "member"}</Badge>
          </div>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3 w-full"
            onClick={async () => {
              await logout();
              router.replace("/login");
            }}
          >
            Sign out
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          <div className="flex items-center justify-between">
            <Link href="/jobs" className="text-base font-semibold">
              ScrapeFlow
            </Link>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await logout();
                router.replace("/login");
              }}
            >
              Sign out
            </Button>
          </div>
          <nav className="mt-2 flex gap-1 overflow-x-auto pb-1">
            {NAV.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`whitespace-nowrap rounded-md px-2.5 py-1.5 text-xs font-medium ${
                    active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
