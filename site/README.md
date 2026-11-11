# ScrapeFlow documentation site

The static landing page and documentation site for
[ScrapeFlow](https://github.com/webd2276/Scrap-Flow). It explains the project,
reproduces the setup guide from `SETUP.md`, lists what is verified versus
unverified, and previews the 37-page project deck in the browser.

Built with Vite, React 18, TypeScript and Tailwind CSS. There is no backend, no
database and no analytics: `npm run build` produces a folder of static files.

## Run it

Node.js 22+ is recommended.

```bash
cd site
npm install
npm run dev        # http://localhost:5173
```

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server with hot reload |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run build` | Type-checks, then writes the production build to `dist/` |
| `npm run preview` | Serves `dist/` locally |

## Where the content lives

All copy is typed data, so text can be edited without touching layout code.

```
src/
  data/
    site.ts            nav, hero, stats, features, security, verified scope, screenshots, FAQ
    architecture.ts    architecture layers and request lifecycle
    stack.ts           tech-stack tab rows
    setup/
      types.ts         SetupBlock union and the 7.0 intro note
      gettingStarted.ts  7.1 – 7.6
      configuration.ts   7.7 – 7.9
      operations.ts      7.10 – 7.15
      index.ts         combines the setup sections in order
  components/          one component per section, plus shared UI
  lib/                 theme, scroll spy, clipboard, asset URL, className helper
```

`src/data/site.ts` also holds `REPO_URL`, `PRESENTATION_FILE` and
`PRESENTATION_PAGES`. Change the repository URL or deck page count there, once.

## Replace the presentation PDF

The viewer loads the file listed in `PRESENTATION_FILE`
(`ScrapeFlow-Project-Presentation.pdf` by default).

1. Export the new deck as a **16:9** PDF.
2. Overwrite `site/public/ScrapeFlow-Project-Presentation.pdf`.
3. If the filename changes, update `PRESENTATION_FILE` in `src/data/site.ts`.
4. If the page count changes, update `PRESENTATION_PAGES` in the same file. This
   is the number shown by the skeleton and the page field before the PDF
   finishes loading; the viewer switches to the real count once parsed.
5. Run `npm run build`. The file is copied unchanged into `dist/`.

Also update the link preview image (`site/public/og-cover.png`, 1200×630 is the
usual target) if the deck's cover changed.

The viewer is lazy-loaded: `pdfjs-dist` is only fetched when the presentation
section approaches the viewport. If PDF.js fails, the section falls back to an
`<iframe>` plus **Download PDF** and **Open in new tab** links, so the deck is
never unreachable.

## Add or replace screenshots

The gallery reads from the `SCREENSHOTS` array in `src/data/site.ts`. Each entry
has a `slug`, `title`, `blurb` and a path relative to `public/`.

1. Drop the image into `site/public/screenshots/`.
2. Add or edit the entry, for example:

   ```ts
   {
     slug: "webhooks",
     title: "Webhook deliveries",
     blurb: "Signed deliveries, retries and dead letters.",
     file: "screenshots/webhooks.png",
   }
   ```

3. Keep screenshots free of real secrets, tokens, customer data and internal
   hostnames.

Missing files do not break the layout: the card swaps to a labelled gradient
placeholder when an image fails to load. Screenshots are lazy-loaded, and the
lightbox supports arrow keys and Escape.

## Update the setup guide

`SETUP.md` at the repository root is the source of truth. When it changes, edit
the matching typed blocks under `src/data/setup/`:

- `paragraph`, `subheading`, `list`, `table`
- `code` — needs a `language` (`bash`, `powershell`, `cmd`, `json`, `dotenv`,
  `yaml`, `text`, `python`, `typescript`) and an optional `label`
- `callout` — `info`, `warn` or `danger`
- `tabs` — used for the four-OS quick start
- `accordion` — set `filterable: true` for the 17-row troubleshooting table
- `checklist` — interactive, stored in memory only

Inline formatting supports `` `code` ``, `**bold**` and `[label](https://link)`
only. Everything is escaped; no raw HTML is rendered.

## Project structure and build notes

- `base: "./"` in `vite.config.ts`, so the build works at a domain root or under
  a GitHub Pages project path. Runtime files in `public/` are resolved through
  `assetUrl()` in `src/lib/asset.ts` — use it instead of hardcoding `/file.pdf`.
- The PDF worker is imported with Vite's `?url` suffix, which copies and hashes
  `pdf.worker.min.mjs` into `dist/assets/`.
- Both heavy dependencies load on demand: the PDF viewer when its section
  approaches the viewport, and `prism-react-renderer` when a code block does.
- Code blocks use `prism-react-renderer` and stay dark in both themes for
  predictable contrast.
- The theme is stored under `sf-theme` in `localStorage`; a small inline script
  in `index.html` applies it before first paint.
- `prefers-reduced-motion` disables the reveal animation, count-up and smooth
  scrolling.

## Deploying

Any static host works. Build first:

```bash
cd site
npm run build
```

Then publish `site/dist/`. For GitHub Pages, upload the contents of `dist/` (or
use an Actions workflow). Because the base is relative, no sub-path rewrite is
needed.

## What this site does not claim

The deck, the setup guide and the verified/unverified lists deliberately match
the project's own evidence. Do not add testimonials, customer counts, uptime
figures or performance numbers that were not measured. Anything that needs an
external service or a different operating system stays in the "Not verified"
column until someone actually runs it.
