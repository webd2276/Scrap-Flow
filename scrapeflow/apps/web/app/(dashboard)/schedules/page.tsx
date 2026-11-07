import type { ReactNode } from "react";

import { ScheduleManager } from "@/components/schedule-manager";

export default function SchedulesPage(): ReactNode {
  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Schedules</h1>
        <p className="mt-1 text-sm text-slate-500">
          Run scrapes and automations on a cron schedule, watch fields for changes, and
          export run history.
        </p>
      </div>
      <ScheduleManager />
    </div>
  );
}
