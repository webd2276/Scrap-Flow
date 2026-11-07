import type { ReactNode } from "react";

import { ApiKeyManager } from "@/components/api-key-manager";

export default function KeysPage(): ReactNode {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">API keys</h1>
        <p className="mt-1 text-sm text-slate-500">
          Create scoped bearer tokens for scripts and integrations. Keys are hashed at
          rest and shown only once.
        </p>
      </div>
      <ApiKeyManager />
    </div>
  );
}
