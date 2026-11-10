# Integration hand-off

## Frontend
- Project: `site/`
- Install: `npm ci` (working directory: `site/`)
- Build: `npm run build` (working directory: `site/`)
- Dev: `npm run dev` (working directory: `site/`)
- Test: `npm test` (working directory: `site/`)
- API seam: none; this is a static Astro showcase with no backend API.
- Mock data/client files to delete: none.

## Backend and API
- Backend project, run/build commands, port, and health endpoint: not applicable (frontend-only).
- Route inventory: `GET /` (Overview), `GET /project/` (Project), `GET /resources/` (Resources); statically generated HTML.

## Data and shared types
- Database: none; migrations: not applicable; **NO seed data**.
- Shared types package: none; content types are local to `site/src/data/`.
- Authentication and application-managed storage: none.

## Services
- Essential: static Astro site and GitHub Pages Actions build/deploy workflow.
- Enhancement: none.
- Azure services: none.
- Repository document links are generated from `PUBLIC_REPOSITORY_URL` and `PUBLIC_REPOSITORY_BRANCH` in the Pages workflow; no credentials or deployment secrets are required by the site.
