const base = import.meta.env.BASE_URL;

/**
 * Resolve a file in `public/` against the configured Vite base. Keeping every
 * runtime asset URL behind this helper is what lets the same build run at a
 * domain root or under a GitHub Pages project path.
 */
export function assetUrl(path: string): string {
  const prefix = base.endsWith("/") ? base.slice(0, -1) : base;
  const suffix = path.startsWith("/") ? path.slice(1) : path;
  return `${prefix}/${suffix}`;
}
