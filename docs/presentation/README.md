# ScrapeFlow — project presentation

A 37-slide, 16:9 deck that walks through the whole ScrapeFlow project: product,
architecture, languages, package managers, backend libraries, frontend libraries,
live artifacts, quality gates, the Strix security-scanning integration and the
honestly-unverified external paths.

**Deliverable:** [`ScrapeFlow-Project-Presentation.pdf`](ScrapeFlow-Project-Presentation.pdf)
(37 pages, 1200 × 675 pt).

## Layout

| Path | Purpose |
| --- | --- |
| `src/*.html` | Slide source, split by section so each part stays editable. |
| `build.py` | Concatenates the parts and injects the per-slide "In short" strip. |
| `presentation.html` | Generated deck (open in a browser to review). |
| `assets/` | Real captured screenshots and the downloaded job artifacts. |
| `evidence/` | Raw command output used on the quality and metrics slides. |

## Rebuild

```bash
python3 docs/presentation/build.py
```

Then render the PDF with Playwright's Chromium. Run the script from
`scrapeflow/apps/web` so Node resolves the local `playwright` package:

```js
// render.mjs
import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto('file:///…/docs/presentation/presentation.html', { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(800);
await page.pdf({
  path: '…/docs/presentation/ScrapeFlow-Project-Presentation.pdf',
  width: '1600px',
  height: '900px',
  printBackground: true,
  preferCSSPageSize: true,
});
await browser.close();
```

`build.py` aborts if the fragment count no longer matches 37 slides, so a lost
slide fails the build instead of shipping a short deck.

## Provenance of the artifacts

- Screenshots `01`–`11` were captured with Playwright at 2× DPR from the running
  Compose stack (API on `:8000`, web on `:3000`).
- `screenshot.png`, `page.html` and `result.json` are the real artifacts of job
  `d59d6ef5-1868-4e10-8999-96e762cfdc6e` (`https://quotes.toscrape.com/`,
  `render_js=true`), downloaded through the presigned-URL endpoint.
- `evidence/*` is verbatim command output; nothing on the quality slides is typed
  by hand.

## Deliberately marked unverified

Live Stripe checkout, the official MinIO image and lifecycle rules, the Caddy
production topology, a commercial proxy gateway, a real external webhook
receiver, hosted GitHub Actions and a real Locust capacity run were not available
in this environment. The deck labels those paths as unverified rather than
presenting them as proven. The same applies to the Strix pentest integration:
the workflow and all three runners are committed and tested, but no scan has run
without an LLM key.
