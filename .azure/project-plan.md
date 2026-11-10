# Project Plan

**Status**: Approved
**Created**: 2026-11-10
**Mode**: AUGMENT

---

## 1. Project Overview

**Goal**: Add a responsive, English-language, clean-light static showcase and documentation site for the existing ScrapeFlow project, published with GitHub Pages and accompanied by a GitHub Actions Pages workflow. The site will summarize documented capabilities and verification evidence without copying setup instructions, private configuration, credentials, or deployment-only details. The project is designed so that every page and content component is independently testable.

**App Type**: Static website (frontend only)

**API Login**: No

**Mode**: AUGMENT

**Deployment Plan**: No deployment plan found

---

## 2. Frontend — Web App

| Component | Technology |
|-----------|-----------|
| **Language** | TypeScript |
| **Framework** | Astro |
| **Package Manager** | npm |
| **Test Runner** | Vitest |
| **Mocking Library** | vi.mock |
| **Test Command** | npm test |

---

## 3. Services Required

No Azure services, backend, database, authentication, or application-managed storage are required. GitHub Pages is the selected external static host; a repository workflow will build and publish the site using GitHub's Pages deployment mechanism. The plan does not assume custom deployment secrets.

| Azure Service | Role in App | Environment Variable | Default Value (Local) | Classification |
|---------------|-------------|----------------------|-----------------------|----------------|
| None required | Static content only; GitHub Pages is external hosting, not an Azure dependency | — | — | Not applicable |

---

## 4. Prerequisites

Double-check all tools marked ❓ before proceeding.

### Run

| Tool | Service(s) | Installed | Version |
|------|------------|-----------|---------|
| Node.js | frontend | ✅ | v24.22.1 |
| npm | frontend | ✅ | 11.19.1 |
| Git | frontend | ✅ | 2.53.0 |

### Debug

| Tool | Service(s) | Installed | Version |
|------|------------|-----------|---------|
| VS Code JavaScript debugger | frontend | ❓ | Unknown |

---

## 5. Design System & UI

**Component Library**: Pico.css with native semantic HTML
**Style Direction**: Clean, light editorial showcase with generous whitespace, restrained teal branding, warm amber accents, fine borders, and subtle elevation. Prioritize readable project storytelling and clear links to the repository over a dense product dashboard.
**Typography**: Inter when available, system-ui fallback
**Content Language**: English

### Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `primary` | `#176B73` | ScrapeFlow links, primary actions, and active navigation |
| `accent` | `#D97735` | Small highlights and secondary calls to action |
| `surface` | `#F7FAF9` | Light page background |
| `text` | `#172B2D` | Main titles and readable body text |
| `muted` | `#5D7071` | Captions, supporting copy, and metadata |
| `border` | `#DCE6E3` | Card edges, separators, and understated dividers |

### Pages

| Page | Route | Purpose | Layout |
|------|-------|---------|--------|
| Overview | `/` | Introduce ScrapeFlow and summarize dated, locally verified evidence without implying hosted CI has passed. | `header, nav, hero, grid, card-list, footer` |
| Project | `/project/` | Summarize documented platform components and workflow at a high level. | `header, nav, main, split(card-list\|grid), footer` |
| Resources | `/resources/` | Link to repository documentation and the project presentation without copying setup or operational content into the showcase. | `header, nav, main, card-list, actions, footer` |

### Sample Content

Overview — ScrapeFlow report highlights:
| Highlight | Value | Context | Status |
|-----------|-------|---------|--------|
| Automated checks | 322 passed, 3 skipped | Local verification report dated 2026-11-08 | Reported locally |
| Branch and line coverage | 83.08% | Local verification report dated 2026-11-08 | Reported locally |
| Browser automation | Selenium Grid with Celery workers | High-level capability documented in the final report | Implemented |
| Hosted GitHub Actions run | Not observed in the report | Do not imply hosted CI has passed | Unverified |

Project — documented platform capabilities:
| Area | Technology or capability | Summary | Status |
|------|---------------------------|---------|--------|
| API | FastAPI | Control plane for scraping and automation jobs | Implemented |
| Job execution | Celery workers | Background execution for queued work | Implemented |
| Browser path | Selenium Grid | Browser-driven page interaction | Implemented |
| Web dashboard | Next.js | User-facing project dashboard | Implemented |

Resources — repository documents and artifact:
| Resource | Repository path | Description |
|----------|----------------|-------------|
| Setup guide | `SETUP.md` | Link to the repository document only; do not reproduce setup procedures or configuration |
| Final report | `docs/FINAL_REPORT.md` | Link to dated implementation and verification summary, including unverified items |
| Presentation guide | `docs/presentation/README.md` | Link to presentation contents and artifact notes |
| Project presentation | `docs/presentation/ScrapeFlow-Project-Presentation.pdf` | Link to the existing 37-slide project presentation |

---

## 6. Project Structure

```text
site/
├── astro.config.mjs
├── package.json
├── tsconfig.json
├── src/
│   ├── components/
│   │   ├── SiteHeader.astro
│   │   ├── SiteFooter.astro
│   │   ├── HighlightCard.astro
│   │   └── ResourceCard.astro
│   ├── layouts/
│   │   └── BaseLayout.astro
│   ├── pages/
│   │   ├── index.astro
│   │   ├── project.astro
│   │   └── resources.astro
│   ├── data/
│   │   └── project-highlights.ts
│   └── styles/
│       └── global.css
├── tests/
│   └── project-content.test.ts
└── public/
    └── favicon.svg
.github/
└── workflows/
    └── pages.yml
```

The Pages workflow should build `site/` as a static Astro site, upload the generated `dist/` artifact, and deploy it using GitHub Pages. Configure the repository's Pages source as GitHub Actions. Set Astro's `site` and `base` for project-site paths so assets and internal links work under the repository subpath. Link repository documentation and the existing PDF rather than copying setup-only content, private configuration, or credentials into the public site.

---

## 7. Route Definitions

| # | Method | Path | Description | Request Body | Response Body | Status Codes |
|---|--------|------|-------------|-------------|--------------|-------------|
| 1 | GET | `/` | Static ScrapeFlow overview and dated report highlights | — | Generated HTML page | 200 |
| 2 | GET | `/project/` | Static high-level capabilities overview | — | Generated HTML page | 200 |
| 3 | GET | `/resources/` | Static links to repository documentation and presentation | — | Generated HTML page | 200 |

---

## 8. Next Steps

1. Review and explicitly approve this plan and its clean-light, English-language direction.
2. After approval, scaffold the Astro site and GitHub Pages workflow without changing the existing ScrapeFlow application.
3. Verify the static build and tests locally, then verify the Pages workflow and published routes in the repository; distinguish local results from hosted results.
