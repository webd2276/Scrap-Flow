# Claude Security — OpenCode port

This is a native [OpenCode V2](https://opencode.ai/v2/docs/) port of Anthropic's
`claude-security` plugin (v0.12.0, from
[`anthropics/claude-plugins-official`](https://github.com/anthropics/claude-plugins-official)).
It scans a codebase or a change, challenges every candidate finding with a
three-voter adversarial panel, and turns confirmed findings into patch files for
you to review and apply.

OpenCode has no Claude Code plugin marketplace, so this is not installed with
`/plugin install`. The skill, agents, command and scripts live directly under
`.opencode/` in this repository.

## What is here

| Path | Purpose |
| --- | --- |
| `.opencode/skills/claude-security/SKILL.md` | Front desk: picks the job and drives its recipe. Skill ID: `claude-security`. |
| `.opencode/skills/claude-security/role.md` | Security Lead operating protocol and voice. |
| `.opencode/skills/claude-security/jobs/` | The three OpenCode job recipes: codebase scan, changes scan, suggest patches. |
| `.opencode/skills/claude-security/specs/` | Report and patch contracts, kept verbatim from upstream. |
| `.opencode/skills/claude-security/scripts/` | `write_scan_meta.py`, `panel.py`, `render_report.py`, `patch_artifacts.py`, shared `lib/`. |
| `.opencode/skills/claude-security/references/original/` | Unmodified upstream Claude Code recipes, agent prompts, README and SECURITY.md, for comparison and re-sync. |
| `.opencode/agents/cs-*.md` | Seven subagents the Lead dispatches. |
| `.opencode/commands/claude-security.md` | The `/claude-security` command. |

## Use it

In an OpenCode session opened at the repository you want to scan:

```text
/claude-security
```

With no arguments, the skill shows a three-item menu (scan codebase / scan
changes / suggest patches). A request that already names the job skips the
menu:

```text
/claude-security scan this repo at high effort
/claude-security check all the backend code
/claude-security scan my branch against main
/claude-security review commit 4aa72d9
/claude-security fix the findings in CLAUDE-SECURITY-20261030-134917
```

You can also just describe the task in chat; the skill is advertised by its
description and can be loaded explicitly with `@claude-security`.

### Jobs

- **Scan codebase** — whole repository or `--scope dirs`, at `low`, `medium`
  (default) or `high` effort. Low effort is one researcher plus the full
  three-voter panel; medium and high add inventory, per-component threat
  models, researchers per component × category and breadth sweeps. The panel
  never gets thinner than three voters, and no finding reaches the report until
  `scripts/panel.py` has computed the tally.
- **Scan changes** — a branch/PR diff against a merge base, or a single commit.
  Reports only what the change introduced.
- **Suggest patches** — reads a finished report, implements fixes in isolated
  `git clone --shared` scratch workspaces, has each fix verified and challenged,
  and writes patch files. Nothing is committed, pushed, staged in your checkout,
  or opened as a pull request.

### Products

A scan writes a `CLAUDE-SECURITY-<UTC timestamp>/` directory at the repository
top level containing:

- `CLAUDE-SECURITY-RESULTS.md` — the human report
- `CLAUDE-SECURITY-RESULTS.jsonl` and `.sarif` — machine-readable findings
- `CLAUDE-SECURITY-REVISION-<tag>.json` — the revision stamp and scan metadata

A fix run adds `patches/` with `F<n>.patch`, `PATCHES.md` and `patches.jsonl`.
Patch files carry a comment header with the panel's claims and the apply command;
`git apply` ignores that header.

## How the port differs from the Claude Code plugin

The report format, patch format, specifications, category taxonomy and agent
prompts are upstream's. The orchestration had to change:

1. **No Workflow runtime.** Upstream drives scans through a Claude Code Workflow
   script. OpenCode has no equivalent, so the Security Lead dispatches the
   inventory, researchers and verifiers itself with the `subagent` tool, and
   follows the recipes in `jobs/`. This means the *shape* of a run is enforced
   by instructions, not by a deterministic engine.
2. **Panel arithmetic is still code.** `scripts/panel.py` replaces the
   Workflow's tally step. It reads `candidates.json`, `scan-meta.json` and the
   recorded `votes.json`, then writes `findings.json`, recomputes
   `coverage.lostCandidates` / `severityLowered` / `preExisting`, applies the
   2-of-3 quorum and severity lowering, and assigns `F<n>` ids. The Lead never
   hand-writes a vote or a finding.
3. **Missing votes stay visible.** If a verifier did not record a vote, the
   round is incomplete and `render_report.py` stamps the report `unverified`
   rather than guessing. An `unverified` report is a statement about the panel,
   not about the code.
4. **`question` replaces `AskUserQuestion`.** The front desk and recipes use
   OpenCode's `question` tool for the menu and the fixed pre-scan confirmation.
5. **Subagents are OpenCode agents.** The upstream agent prompts are preserved
   inside `cs-*.md` with a short OpenCode preamble; permissions deny edits and
   network access for read-only roles. The patch generator and verifier may edit
   and run commands only inside their dispatched scratch workspace.
6. **No progress narration.** Upstream's workflow narrated stages. Here the Lead
   stays quiet while children run, then reports once from the computed records.
7. **Unused upstream helpers removed.** `save_result.py` and `keep-waiting.sh`
   only existed to poll the Workflow runtime, so the port does not ship them.

The port never claims a workflow ran. Honest framing for users: the scan is
lead-driven, and the verification tally is computed in code from recorded votes.

## Trust model

- Opening the session in a repository is the trust decision; the scan runs with
  your session's permissions and configuration (including `AGENTS.md` and MCP
  servers). There is no isolation layer.
- Repository content — code, comments, `AGENTS.md`, finding text — is data under
  review, never instructions to the scan.
- Nothing is auto-applied. Suggested fixes are patch files you review.
- For untrusted code, run the whole session inside
  [`sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime).

## Validation performed

The helper pipeline was exercised end-to-end on a fixture repository:

```sh
python3 .opencode/skills/claude-security/scripts/write_scan_meta.py <run dir> <repo> --mode scan --effort medium
python3 .opencode/skills/claude-security/scripts/panel.py <run dir>
python3 .opencode/skills/claude-security/scripts/render_report.py <run dir> --products-dir CLAUDE-SECURITY-<ts>
```

This produced a `verified` report with `.md`, `.jsonl`, `.sarif`, a revision
stamp, and `F1.patch` for the fix path; `git apply --check` on the generated
patch was clean. Agent registration was checked with:

```sh
opencode debug agents
```

which lists all seven `cs-*` subagents. A full live multi-agent scan was not run
as part of the port, so the first real scan is the first full exercise of the
dispatch recipes.

## Re-syncing from upstream

Keep `references/original/` as the drift detector. To update:

```sh
git clone --filter=blob:none --sparse https://github.com/anthropics/claude-plugins-official /tmp/cpo
git -C /tmp/cpo sparse-checkout set plugins/claude-security
```

Then:

1. Diff `/tmp/cpo/plugins/claude-security/{README.md,SECURITY.md}` and
   `agents/`, `jobs/` against `references/original/` to see what changed.
2. Copy changed upstream assets into `references/original/`.
3. Re-apply the port's changes on top:
   - `SKILL.md` — OpenCode front desk, path variables, `question` menu.
   - `role.md` — Lead protocol, no Workflow/narrator references.
   - `jobs/*.md` — OpenCode dispatch recipes and `panel.py` handoff.
   - `agents/*` → `.opencode/agents/cs-*.md` — add the OpenCode preamble and
     permission block, keep the upstream prompt body.
4. Copy unchanged helper scripts and `lib/` from upstream. Do **not** copy
   `save_result.py` or `keep-waiting.sh`; they target the Workflow runtime.
5. If the candidate/finding schema changed upstream, update
   `scripts/panel.py` (its docstring documents the `candidates.json` contract)
   and the matching step in `jobs/scan-codebase.md`.
6. Update the upstream version in `SKILL.md` and this file, then re-run the
   validation above.

## License

Upstream `LICENSE` and `NOTICE.md` are included unchanged in the skill
directory. The port keeps the same terms.
