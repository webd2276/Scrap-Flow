export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ErrorEnvelope {
  error?: {
    code?: unknown;
    message?: unknown;
    details?: unknown;
  };
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let payload: ErrorEnvelope | null = null;
  try {
    payload = (await response.json()) as ErrorEnvelope;
  } catch {
    payload = null;
  }
  const code =
    typeof payload?.error?.code === "string" ? payload.error.code : `HTTP_${response.status}`;
  const message =
    typeof payload?.error?.message === "string"
      ? payload.error.message
      : response.statusText || "Request failed";
  return new ApiError(response.status, code, message, payload?.error?.details);
}

export async function readJson<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Billing redirects must never downgrade to http or execute a script URL even
 * if the API response is tampered with. Host allowlisting is optional so the
 * check stays useful for deployments that front Stripe with their own domain.
 */
export function isSafeHttpsUrl(
  value: string,
  allowedHosts?: readonly string[],
): boolean {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return false;
  }
  if (parsed.protocol !== "https:") return false;
  if (allowedHosts && !allowedHosts.includes(parsed.hostname)) return false;
  return true;
}
