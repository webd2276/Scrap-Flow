import type { SetupSubsection } from "./types";

export const GETTING_STARTED: SetupSubsection[] = [
  {
    id: "prerequisites",
    number: "7.1",
    title: "Prerequisites",
    blocks: [
      { type: "subheading", text: "Required for the Docker setup" },
      {
        type: "table",
        head: ["Tool", "Linux", "macOS", "Windows"],
        rows: [
          ["Docker Engine 24+", "required", "Docker Desktop", "Docker Desktop"],
          ["Docker Compose v2", "required", "included", "included"],
          ["Git", "required", "required", "required"],
          ["Bash 3.2+", "required by `run.sh`", "built in", "not needed for `run.ps1`"],
          ["PowerShell 5.1+", "optional", "optional", "required for `run.ps1`"],
          ["curl", "required by `run.sh`", "required by `run.sh`", "not needed by `run.ps1`"],
          ["jq", "optional (API examples)", "optional", "optional"],
          ["Disk space", "~10 GB free", "~10 GB free", "~10 GB free"],
          ["RAM", "8 GB recommended", "8 GB recommended", "8 GB recommended"],
        ],
      },
      { type: "subheading", text: "Required only for local development or tests" },
      {
        type: "table",
        head: ["Tool", "Version", "Check"],
        rows: [
          ["Python", "3.12", "`python3 --version`"],
          ["uv", "0.13+", "`uv --version`"],
          ["Node.js", "22+", "`node --version`"],
          ["npm", "10+", "`npm --version`"],
        ],
      },
      { type: "subheading", text: "Platform notes" },
      {
        type: "list",
        items: [
          "**Windows native:** use `scripts\\run.ps1` or `scripts\\run.cmd`. It needs Docker Desktop and PowerShell only; it generates `.env` itself and does not require Bash, Python, or curl.",
          "**Windows WSL 2 / Git Bash:** use `./scripts/run.sh`. WSL needs Docker integration enabled in Docker Desktop.",
          "**macOS:** use `./scripts/run-macos.sh`, which delegates to the shared `run.sh`. `python3` is only needed to create `.env` or run `fix-db-password`; install it with `xcode-select --install` or `brew install python`.",
        ],
      },
    ],
  },
  {
    id: "get-the-project",
    number: "7.2",
    title: "Get the project",
    blocks: [
      {
        type: "paragraph",
        text: "Clone the repository and move into the application directory. All later commands run from inside `scrapeflow/` unless a step says otherwise.",
      },
      {
        type: "code",
        language: "bash",
        label: "Clone and enter the app root",
        code: "git clone https://github.com/webd2276/Scrap-Flow.git web-scrapping-tool\ncd web-scrapping-tool/scrapeflow",
      },
      {
        type: "paragraph",
        text: "Windows: `cd web-scrapping-tool\\scrapeflow`. Confirm you are in the right place:",
      },
      {
        type: "code",
        language: "bash",
        label: "Verify the working directory",
        code: "pwd   # .../web-scrapping-tool/scrapeflow",
      },
      {
        type: "callout",
        tone: "info",
        title: "Repository root vs application root",
        text: "The Git root holds `scrapeflow/`, `docs/`, `SETUP.md` and `.github/`. Application commands, Compose files and `.env` all live under `scrapeflow/`.",
      },
    ],
  },
  {
    id: "quickstart",
    number: "7.3",
    title: "Fastest start — one command",
    blocks: [
      {
        type: "paragraph",
        text: "The included runners build the images, create `.env` with random secrets if it is missing, start every service, and wait until the API and dashboard answer. All three platforms share the same Compose files and the same commands.",
      },
      {
        type: "tabs",
        tabs: [
          {
            label: "Linux",
            blocks: [
              {
                type: "code",
                language: "bash",
                label: "Linux",
                code: "./scripts/run.sh",
              },
            ],
          },
          {
            label: "macOS",
            blocks: [
              {
                type: "code",
                language: "bash",
                label: "macOS",
                code: "./scripts/run-macos.sh",
              },
              {
                type: "paragraph",
                text: "The wrapper checks Docker Desktop, the daemon and `strix`, then delegates to `run.sh` so the two platforms cannot drift.",
              },
            ],
          },
          {
            label: "Windows PowerShell",
            blocks: [
              {
                type: "code",
                language: "powershell",
                label: "PowerShell 5.1+",
                code: "powershell -ExecutionPolicy Bypass -File .\\scripts\\run.ps1",
              },
            ],
          },
          {
            label: "Windows CMD",
            blocks: [
              {
                type: "code",
                language: "cmd",
                label: "Command Prompt",
                code: "scripts\\run.cmd",
              },
            ],
          },
        ],
      },
      { type: "subheading", text: "What the runner does" },
      {
        type: "list",
        ordered: true,
        items: [
          "Check Docker and Compose v2 (and curl on Linux/macOS).",
          "Create `.env` with random secrets when missing.",
          "Try the pinned MinIO image. If it cannot be pulled, fall back to the `adobe/s3mock` container so the stack still works locally.",
          "Build and start `postgres`, `redis`, `minio`, `migrate`, `minio-init`, `api`, `worker`, `beat`, `egress-proxy`, `selenium`, and `web`.",
          "Wait for `http://127.0.0.1:8000/ready`.",
          "Print the URLs.",
        ],
      },
      { type: "subheading", text: "Runner commands" },
      {
        type: "table",
        head: ["Action", "Linux / macOS", "Windows PowerShell"],
        rows: [
          ["Start or update", "`./scripts/run.sh`", "`.\\scripts\\run.ps1`"],
          ["Container status", "`./scripts/run.sh status`", "`.\\scripts\\run.ps1 status`"],
          ["Follow logs", "`./scripts/run.sh logs`", "`.\\scripts\\run.ps1 logs`"],
          ["Seed demo data", "`./scripts/run.sh seed`", "`.\\scripts\\run.ps1 seed`"],
          ["Repair DB password", "`./scripts/run.sh fix-db-password`", "`.\\scripts\\run.ps1 fix-db-password`"],
          ["Stop (keep data)", "`./scripts/run.sh stop`", "`.\\scripts\\run.ps1 stop`"],
          ["Stop and delete data", "`./scripts/run.sh reset`", "`.\\scripts\\run.ps1 reset`"],
        ],
      },
      { type: "subheading", text: "If PowerShell blocks the script" },
      {
        type: "paragraph",
        text: "The execution policy can refuse to run `.ps1` files. Use the launcher or pass the policy explicitly:",
      },
      {
        type: "code",
        language: "powershell",
        label: "Execution-policy workaround",
        code: "scripts\\run.cmd\n# or\npowershell -ExecutionPolicy Bypass -File .\\scripts\\run.ps1",
      },
      { type: "subheading", text: "Force a storage mode" },
      {
        type: "paragraph",
        text: "Use this when the automatic MinIO choice is not what you want.",
      },
      {
        type: "code",
        language: "bash",
        label: "Linux / macOS",
        code: "SF_S3_MODE=s3mock ./scripts/run.sh   # always use the S3 mock\nSF_S3_MODE=minio  ./scripts/run.sh   # require real MinIO",
      },
      {
        type: "code",
        language: "powershell",
        label: "Windows PowerShell",
        code: "$env:SF_S3_MODE = 's3mock'; .\\scripts\\run.ps1\n$env:SF_S3_MODE = 'minio';  .\\scripts\\run.ps1",
      },
      {
        type: "code",
        language: "cmd",
        label: "Windows CMD",
        code: "set SF_S3_MODE=s3mock\nscripts\\run.cmd",
      },
      { type: "subheading", text: "Give the stack more time" },
      {
        type: "code",
        language: "bash",
        label: "Slow machine",
        code: "SF_HEALTH_TIMEOUT=420 ./scripts/run.sh",
      },
      {
        type: "code",
        language: "powershell",
        label: "Slow machine (PowerShell)",
        code: "$env:SF_HEALTH_TIMEOUT = '420'; .\\scripts\\run.ps1",
      },
      {
        type: "callout",
        tone: "warn",
        title: "Verification scope",
        text: "The Linux runner and the macOS wrapper were exercised on Linux. `run.ps1` was syntax-checked and exercised with PowerShell 7.4.6 against the live stack on Linux. Native Windows PowerShell 5.1 + Docker Desktop and native macOS runs were not available in this environment; if your first run differs, the troubleshooting section lists the platform-specific checks.",
      },
      { type: "subheading", text: "Open these URLs" },
      {
        type: "table",
        head: ["Service", "URL"],
        rows: [
          ["Dashboard", "[http://127.0.0.1:3000](http://127.0.0.1:3000)"],
          ["API", "[http://127.0.0.1:8000](http://127.0.0.1:8000)"],
          ["API docs (development only)", "[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)"],
          ["API metrics", "[http://127.0.0.1:8000/metrics](http://127.0.0.1:8000/metrics)"],
          ["Selenium Grid", "[http://127.0.0.1:4444/status](http://127.0.0.1:4444/status)"],
          ["MinIO console (when using MinIO)", "[http://127.0.0.1:9001](http://127.0.0.1:9001)"],
        ],
      },
    ],
  },
  {
    id: "manual-docker",
    number: "7.4",
    title: "Manual Docker setup",
    blocks: [
      {
        type: "paragraph",
        text: "Use this path if you do not want the runner script.",
      },
      { type: "subheading", text: "4.1 Create .env" },
      {
        type: "code",
        language: "bash",
        label: "Generate .env",
        code: "python3 scripts/generate_env.py",
      },
      {
        type: "paragraph",
        text: "On Windows, the native runner creates `.env` without Python, or use `py -3 scripts\\generate_env.py`.",
      },
      {
        type: "code",
        language: "powershell",
        label: "Generate .env on Windows",
        code: "py -3 scripts\\generate_env.py",
      },
      {
        type: "paragraph",
        text: "This writes `scrapeflow/.env` with mode `600` (or a restricted NTFS ACL on Windows) and random values for the required secrets. It refuses to overwrite an existing file. Never commit `.env`.",
      },
      { type: "subheading", text: "Review it before starting" },
      {
        type: "code",
        language: "bash",
        label: "Review .env with secrets redacted",
        code: "grep -E '^(APP_ENV|POSTGRES_|DATABASE_URL|REDIS_URL|API_KEY_PEPPER|JWT_SECRET|WEBHOOK_SECRET_KEY|ARTIFACTS_|SELENIUM_REMOTE_URL|EGRESS_PROXY_URL)' .env | sed -E 's/(SECRET|PEPPER|PASSWORD)=.*/\\1=<redacted>/'",
      },
      {
        type: "code",
        language: "powershell",
        label: "PowerShell equivalent",
        code: "Get-Content .env |\n  Where-Object { $_ -match '^(APP_ENV|POSTGRES_|DATABASE_URL|REDIS_URL|API_KEY_PEPPER|JWT_SECRET|WEBHOOK_SECRET_KEY|ARTIFACTS_|SELENIUM_REMOTE_URL|EGRESS_PROXY_URL)' } |\n  ForEach-Object { $_ -replace '(SECRET|PEPPER|PASSWORD)=.*', '$1=<redacted>' }",
      },
      { type: "subheading", text: "4.2 Start the development stack" },
      {
        type: "code",
        language: "bash",
        label: "Compose up",
        code: "docker compose --project-directory . --env-file .env up -d --build",
      },
      {
        type: "paragraph",
        text: "If the pinned MinIO image cannot be pulled, use the platform runner (`./scripts/run.sh`, `./scripts/run-macos.sh`, or `.\\scripts\\run.ps1`) or add the S3-mock override manually. The override example below is for a POSIX shell:",
      },
      {
        type: "code",
        language: "bash",
        label: "S3-mock override",
        code: "cat > /tmp/sf-compose-override.yml <<'YAML'\nservices:\n  minio:\n    image: adobe/s3mock:latest\n    command: []\n    environment:\n      HTTP_PORT: \"9000\"\n      COM_ADOBE_TESTING_S3MOCK_STORE_INITIAL_BUCKETS: scrapeflow\n    healthcheck:\n      test: [\"CMD-SHELL\", \"exit 0\"]\n      interval: 2s\n      timeout: 2s\n      retries: 5\n    ports:\n      - \"127.0.0.1:9000:9000\"\n  minio-init:\n    command: [\"python\", \"-c\", \"print('S3 mock bucket pre-created')\"]\nYAML\n\ndocker compose --project-directory . \\\n  -f docker-compose.yml -f /tmp/sf-compose-override.yml \\\n  --env-file .env up -d --build",
      },
      {
        type: "paragraph",
        text: "Migrations run automatically in the one-shot `migrate` service before the API, worker, and beat start.",
      },
      { type: "subheading", text: "4.3 Optional demo data" },
      {
        type: "code",
        language: "bash",
        label: "Seed",
        code: "docker compose exec api python -m scripts.seed",
      },
      {
        type: "paragraph",
        text: "The seed is idempotent. It creates:",
      },
      {
        type: "list",
        items: [
          "organisation `demo` (slug `demo`)",
          "user `demo@example.com`",
          "an admin-scoped API key, printed **once**",
        ],
      },
      {
        type: "paragraph",
        text: "The demo password is printed only when the user is created for the first time. Re-running the seed creates a new API key instead of changing the password.",
      },
    ],
  },
  {
    id: "verify-stack",
    number: "7.5",
    title: "Verify the stack",
    blocks: [
      {
        type: "code",
        language: "bash",
        label: "Health, readiness, dashboard, metrics",
        code: "curl -fsS http://127.0.0.1:8000/health\ncurl -fsS http://127.0.0.1:8000/ready\ncurl -s -o /dev/null -w 'dashboard=%{http_code}\\n' http://127.0.0.1:3000/login\ncurl -fsS http://127.0.0.1:8000/metrics | head",
      },
      {
        type: "paragraph",
        text: "On Windows use `curl.exe` so PowerShell does not substitute its `Invoke-WebRequest` alias:",
      },
      {
        type: "code",
        language: "powershell",
        label: "Windows PowerShell",
        code: "curl.exe -fsS http://127.0.0.1:8000/health\ncurl.exe -fsS http://127.0.0.1:8000/ready\ncurl.exe -s -o NUL -w \"dashboard=%{http_code}`n\" http://127.0.0.1:3000/login",
      },
      { type: "subheading", text: "Expected" },
      {
        type: "list",
        items: [
          "`/health` → `{\"status\":\"ok\", ...}`",
          "`/ready` → `{\"status\":\"ready\",\"checks\":{\"postgres\":{\"status\":\"ok\"},\"redis\":{\"status\":\"ok\"}}}`",
          "dashboard → `200`",
          "`/metrics` → Prometheus text (may require `METRICS_TOKEN` if you set one)",
        ],
      },
      {
        type: "code",
        language: "bash",
        label: "Container status",
        code: "docker compose --project-directory . --env-file .env ps\n# or\n./scripts/run.sh status",
      },
    ],
  },
  {
    id: "first-scrape",
    number: "7.6",
    title: "First account & first scrape",
    blocks: [
      { type: "subheading", text: "6.1 Dashboard" },
      {
        type: "list",
        ordered: true,
        items: [
          "Open [http://127.0.0.1:3000/signup](http://127.0.0.1:3000/signup).",
          "Accept the Terms of Service.",
          "Submit a URL and selectors on the scrape page.",
        ],
      },
      {
        type: "paragraph",
        text: "The browser only talks to Next.js. The refresh token stays in an httpOnly cookie and the access token stays in memory.",
      },
      { type: "subheading", text: "6.2 API with curl" },
      {
        type: "code",
        language: "bash",
        label: "Sign up and enqueue a scrape",
        code: "EMAIL=\"you-$(date +%s)@example.com\"\n\nTOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/v1/auth/signup \\\n  -H 'Content-Type: application/json' \\\n  -d \"{\n    \\\"org_name\\\": \\\"My Org\\\",\n    \\\"email\\\": \\\"$EMAIL\\\",\n    \\\"password\\\": \\\"correct-horse-battery-staple\\\",\n    \\\"tos_accepted\\\": true\n  }\" | jq -r .access_token)\n\nJOB=$(curl -fsS -X POST http://127.0.0.1:8000/v1/scrape \\\n  -H \"Authorization: Bearer $TOKEN\" \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    \"url\": \"https://example.com/\",\n    \"selectors\": {\"title\": {\"css\": \"title\"}},\n    \"include_html\": true\n  }' | jq -r .job.id)\n\necho \"job=$JOB\"",
      },
      { type: "paragraph", text: "Poll it:" },
      {
        type: "code",
        language: "bash",
        label: "Poll the job",
        code: "curl -fsS \"http://127.0.0.1:8000/v1/jobs/$JOB\" \\\n  -H \"Authorization: Bearer $TOKEN\" | jq '{status, duration_ms, result, error}'",
      },
      {
        type: "paragraph",
        text: "Access tokens expire after **900 seconds**. Log in again when you get `401`:",
      },
      {
        type: "code",
        language: "bash",
        label: "Re-login",
        code: "TOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/v1/auth/login \\\n  -H 'Content-Type: application/json' \\\n  -d \"{\\\"email\\\":\\\"$EMAIL\\\",\\\"password\\\":\\\"correct-horse-battery-staple\\\"}\" \\\n  | jq -r .access_token)",
      },
      { type: "subheading", text: "6.3 Browser scrape" },
      {
        type: "paragraph",
        text: "Add `render_js` and optionally a screenshot:",
      },
      {
        type: "code",
        language: "bash",
        label: "Rendered scrape with artifacts",
        code: "curl -fsS -X POST http://127.0.0.1:8000/v1/scrape \\\n  -H \"Authorization: Bearer $TOKEN\" \\\n  -H 'Content-Type: application/json' \\\n  -d '{\n    \"url\": \"https://example.com/\",\n    \"render_js\": true,\n    \"selectors\": {\"title\": {\"css\": \"title\"}},\n    \"screenshot\": true,\n    \"include_html\": true,\n    \"timeout_seconds\": 60\n  }' | jq .",
      },
      {
        type: "paragraph",
        text: "Artifacts are listed and downloaded through the API:",
      },
      {
        type: "code",
        language: "bash",
        label: "List and download artifacts",
        code: "curl -fsS \"http://127.0.0.1:8000/v1/jobs/$JOB/artifacts\" \\\n  -H \"Authorization: Bearer $TOKEN\" | jq .\n\n# Ask for the download; with S3 this is a 307 to a presigned URL\ncurl -s -D /tmp/artifact-headers -o /dev/null \\\n  \"http://127.0.0.1:8000/v1/artifacts/<ARTIFACT_ID>/download\" \\\n  -H \"Authorization: Bearer $TOKEN\"\ngrep -i '^location:' /tmp/artifact-headers\n\n# Fetch the presigned URL. Compose signs for the internal hostname \"minio\",\n# so map it to localhost when downloading from the host machine.\ncurl -fsS --resolve minio:9000:127.0.0.1 -o result.json \"<PRESIGNED_URL>\"",
      },
      {
        type: "paragraph",
        text: "If the download answers directly (local filesystem store, no `Location` header), fetch it with the bearer token instead:",
      },
      {
        type: "code",
        language: "bash",
        label: "Direct download fallback",
        code: "curl -fsS -o result.json \\\n  \"http://127.0.0.1:8000/v1/artifacts/<ARTIFACT_ID>/download\" \\\n  -H \"Authorization: Bearer $TOKEN\"",
      },
      { type: "subheading", text: "6.4 API keys" },
      {
        type: "paragraph",
        text: "Create a scoped key when you do not want to use a short-lived JWT:",
      },
      {
        type: "code",
        language: "bash",
        label: "Create a scoped key",
        code: "curl -fsS -X POST http://127.0.0.1:8000/v1/keys \\\n  -H \"Authorization: Bearer $TOKEN\" \\\n  -H 'Content-Type: application/json' \\\n  -d '{\"name\":\"automation\",\"scopes\":[\"scrape:write\",\"jobs:read\"]}' | jq .",
      },
      {
        type: "paragraph",
        text: "The plaintext key (`sf_live_...`) is returned once and never stored.",
      },
    ],
  },
];
