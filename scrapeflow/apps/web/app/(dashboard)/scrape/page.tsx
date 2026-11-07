import type { ReactNode } from "react";

import { ScrapeForm } from "@/components/scrape-form";

export default function ScrapePage(): ReactNode {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">New scrape</h1>
        <p className="mt-1 text-sm text-slate-500">
          Extract named fields, page text, links, and meta tags from a public page. Use a
          browser render for JavaScript-heavy sites.
        </p>
      </div>
      <ScrapeForm />
    </div>
  );
}
