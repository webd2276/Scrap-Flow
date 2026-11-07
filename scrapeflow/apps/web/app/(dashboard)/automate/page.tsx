import type { ReactNode } from "react";

import { AutomationBuilder } from "@/components/automation-builder";

export default function AutomatePage(): ReactNode {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">New automation</h1>
        <p className="mt-1 text-sm text-slate-500">
          Build a browser workflow with click, type, wait, extract, and screenshot steps.
          Secrets are interpolated only in type, select, and press steps.
        </p>
      </div>
      <AutomationBuilder />
    </div>
  );
}
