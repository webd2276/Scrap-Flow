export type JobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out";

export type JobKind = "scrape" | "automation";

export interface JobError {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface Job {
  id: string;
  kind: JobKind;
  status: JobStatus;
  url: string;
  result: Record<string, unknown> | null;
  error: JobError | null;
  attempts: number;
  max_attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested_at: string | null;
  duration_ms: number | null;
}

export interface JobAccepted {
  job: Job;
  deduplicated: boolean;
}

export interface JobList {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
}

export interface JobEvent {
  id: string;
  type: string;
  message: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

export interface Artifact {
  id: string;
  job_id: string;
  kind: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  expires_at: string | null;
  created_at: string;
  download_url: string;
}

export interface OrgSummary {
  id: string;
  name: string;
  slug: string;
  role: string;
  plan: string;
}

export interface Me {
  user_id: string;
  email: string;
  display_name: string;
  tos_accepted_at: string | null;
  tos_version: string | null;
  orgs: OrgSummary[];
}

export interface TokenPayload {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  org_id: string;
  role: string;
}

export interface BrowserTokenPayload {
  access_token: string;
  expires_in: number;
  user_id: string;
  org_id: string;
  role: string;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  prefix: string;
  key: string;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
}

export interface Usage {
  plan: string;
  plan_name: string;
  period: string;
  monthly_credits: number;
  used: number;
  remaining: number;
  reset_seconds: number;
  max_concurrency: number;
  max_steps: number;
  max_pages: number;
  artifact_retention_days: number;
  billing_enabled: boolean;
}

export interface Plan {
  code: string;
  name: string;
  monthly_credits: number;
  max_concurrency: number;
  max_steps: number;
  max_pages: number;
  artifact_retention_days: number;
}

export interface Schedule {
  id: string;
  name: string;
  kind: JobKind;
  cron: string;
  timezone: string;
  enabled: boolean;
  template: Record<string, unknown>;
  watched_fields: string[];
  notify_on_change: boolean;
  next_run_at: string;
  last_run_at: string | null;
  last_job_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleList {
  items: Schedule[];
  total: number;
  limit: number;
  offset: number;
}

export interface ScheduleRun {
  id: string;
  schedule_id: string;
  job_id: string | null;
  trigger: string;
  status: string;
  scheduled_for: string;
  credits: number;
  error: string | null;
  values: Record<string, unknown> | null;
  changes: Array<Record<string, unknown>> | null;
  created_at: string;
  finished_at: string | null;
}

export interface ScheduleRunList {
  items: ScheduleRun[];
  total: number;
  limit: number;
  offset: number;
}
