import type { ReactNode } from "react";

import { BillingPanel } from "@/components/billing-panel";

export default function BillingPage(): ReactNode {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Usage and billing</h1>
        <p className="mt-1 text-sm text-slate-500">
          Credits are reserved when a job is accepted and settled when it finishes.
        </p>
      </div>
      <BillingPanel />
    </div>
  );
}
