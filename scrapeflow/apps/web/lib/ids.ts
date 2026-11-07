let counter = 0;

/**
 * Stable client-side id for editable rows and builder steps. These ids never
 * leave the browser; API payloads are rebuilt from the field values.
 */
export function newClientId(prefix: string): string {
  counter += 1;
  const random =
    typeof globalThis.crypto !== "undefined" && "randomUUID" in globalThis.crypto
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${counter}`;
  return `${prefix}-${random}`;
}
