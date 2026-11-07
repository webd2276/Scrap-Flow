import { errorFromResponse } from "./api";

const FALLBACK_NAME = "download";

/** Keep a server-supplied name inside the browser download directory. */
export function safeFilename(name: string, fallback = FALLBACK_NAME): string {
  const cleaned = name
    .replace(/[/\\]/g, "_")
    .replace(/[\u0000-\u001f\u007f]/g, "")
    .trim()
    .slice(0, 128);
  if (!cleaned || cleaned === "." || cleaned === "..") return fallback;
  return cleaned;
}

function filenameFrom(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (encoded?.[1]) {
    try {
      return safeFilename(decodeURIComponent(encoded[1].trim()), fallback);
    } catch {
      return fallback;
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return safeFilename(plain?.[1]?.trim() || fallback, fallback);
}

/**
 * Authenticated downloads must go through fetch so the bearer token can be
 * attached; a plain link would hit the proxy without credentials.
 */
export async function downloadResponse(
  response: Response,
  fallbackName: string,
): Promise<void> {
  if (!response.ok) throw await errorFromResponse(response);
  const blob = await response.blob();
  const filename = filenameFrom(response.headers.get("Content-Disposition"), fallbackName);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000);
}
