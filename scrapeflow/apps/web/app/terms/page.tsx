import Link from "next/link";
import type { ReactNode } from "react";

export default function TermsPage(): ReactNode {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <Link className="text-sm text-slate-600 underline" href="/signup">
        Back to signup
      </Link>
      <h1 className="mt-6 text-2xl font-semibold">Terms of Service and Acceptable Use</h1>
      <p className="mt-2 text-sm text-slate-500">
        Summary for the hosted ScrapeFlow service. Your organisation is responsible for the
        URLs and workflows it submits.
      </p>

      <div className="mt-8 space-y-6 text-sm leading-6 text-slate-700">
        <section>
          <h2 className="text-base font-semibold text-slate-900">Authorised use only</h2>
          <p>
            Use ScrapeFlow only on sites you own, operate, or are authorised to access. Do not
            use it to bypass authentication, paywalls, access controls, or technical measures.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-slate-900">No evasive features</h2>
          <p>
            ScrapeFlow does not solve CAPTCHAs, spoof browser fingerprints, or provide stealth
            tooling. Proxy support is for reliability and regional access, not evasion.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-slate-900">Respect site policies</h2>
          <p>
            Honour robots.txt, terms of service, rate limits, and applicable law. New
            organisations respect robots.txt by default; disabling it requires accepting the
            associated responsibility in the organisation settings.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-slate-900">Data and credentials</h2>
          <p>
            You are responsible for the data you collect and for having a lawful basis to store
            it. Automation secrets are transient and must not be used as a store for
            long-lived credentials.
          </p>
        </section>
        <section>
          <h2 className="text-base font-semibold text-slate-900">Abuse</h2>
          <p>
            Requests, URLs, and timestamps are audited. We may suspend organisations that abuse
            the service or target prohibited content.
          </p>
        </section>
      </div>
    </main>
  );
}
