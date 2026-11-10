#requires -Version 5.1
<#
.SYNOPSIS
    Run a Strix pentest against ScrapeFlow on Windows.

.DESCRIPTION
    Scans the committed source tree in an isolated git worktree, or the running
    API on port 8000. Strix needs Docker Desktop, the strix CLI and an LLM key.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\security-scan.ps1

.EXAMPLE
    .\scripts\security-scan.ps1 live

.EXAMPLE
    .\scripts\security-scan.ps1 --help
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Mode = 'code',

    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptPath = $PSCommandPath
if (-not $ScriptPath) {
    $ScriptPath = $MyInvocation.MyCommand.Path
}
$ScriptDir = Split-Path -Parent $ScriptPath
$Root = (Resolve-Path (Join-Path $ScriptDir '..')).Path
Set-Location $Root

$RunDir = Join-Path $Root '.run'
$Worktree = Join-Path $RunDir 'strix-worktree'
$SpecPath = Join-Path $RunDir 'strix-openapi.json'
$LogDir = Join-Path $Root 'strix_runs'
$ScanMode = if ($env:SF_STRIX_MODE) { $env:SF_STRIX_MODE.ToLowerInvariant() } else { 'quick' }
$Budget = if ($env:SF_STRIX_BUDGET) { $env:SF_STRIX_BUDGET } else { '10' }

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host "==> $Message"
}

function Write-Warn {
    param([string]$Message)
    [Console]::Error.WriteLine("warning: $Message")
}

function Fail {
    param([string]$Message)
    [Console]::Error.WriteLine("error: $Message")
    exit 1
}

function Show-Usage {
    Write-Host @'
Run a Strix pentest against ScrapeFlow on Windows.

Usage:
  .\scripts\security-scan.ps1              scan the committed source tree
  .\scripts\security-scan.ps1 code         same as above
  .\scripts\security-scan.ps1 live         scan the running API on :8000
  .\scripts\security-scan.ps1 --help       show this help

Requirements:
  Docker Desktop running, strix on PATH, STRIX_LLM and LLM_API_KEY set.

Environment:
  $env:SF_STRIX_MODE = "quick"|"standard"|"deep"   scan depth (default: quick)
  $env:SF_STRIX_BUDGET = "10"                      LLM spend cap in USD
  $env:SF_STRIX_KEEP = "1"                         keep the throwaway worktree
  $env:STRIX_TEST_EMAIL, $env:STRIX_TEST_PASSWORD  optional live-test credentials

Install Strix with:
  uv tool install strix-agent==1.7.0

Results are written to strix_runs\. Open them with: strix view

If PowerShell blocks the script, run it with:
  powershell -ExecutionPolicy Bypass -File .\scripts\security-scan.ps1
or use the Command Prompt launcher:
  scripts\security-scan.cmd
'@
}

if ($Help) {
    Show-Usage
    exit 0
}

switch ($Mode.ToLowerInvariant()) {
    'code' { }
    'live' { }
    '-h' { Show-Usage; exit 0 }
    '--help' { Show-Usage; exit 0 }
    'help' { Show-Usage; exit 0 }
    default { Fail "unknown mode '$Mode' (expected 'code' or 'live')" }
}

Write-Step 'Checking prerequisites'

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerCmd) {
    Fail 'docker is not installed or not on PATH; install Docker Desktop for Windows'
}
$DockerExe = if ($dockerCmd.Source) { $dockerCmd.Source } else { $dockerCmd.Path }
& $DockerExe info *> $null
if ($LASTEXITCODE -ne 0) {
    Fail 'the Docker daemon is not running; start Docker Desktop and retry'
}

$strixCmd = Get-Command strix -ErrorAction SilentlyContinue
if (-not $strixCmd) {
    Fail 'strix is not installed or not on PATH; run: uv tool install strix-agent==1.7.0'
}
$StrixExe = if ($strixCmd.Source) { $strixCmd.Source } else { $strixCmd.Path }

if (-not $env:STRIX_LLM) {
    Fail 'STRIX_LLM is not set (for example openrouter/z-ai/glm-5.3)'
}
if (-not $env:LLM_API_KEY) {
    Fail 'LLM_API_KEY is not set'
}

if (@('quick', 'standard', 'deep') -notcontains $ScanMode) {
    Fail "SF_STRIX_MODE must be quick, standard or deep (got '$ScanMode')"
}
if ($Budget -notmatch '^[0-9]+(\.[0-9]+)?$') {
    Fail "SF_STRIX_BUDGET must be a number (got '$Budget')"
}

$strixArgs = @('-n')
$worktreeCreated = $false

if ($Mode.ToLowerInvariant() -eq 'live') {
    Write-Step 'Checking the local stack'
    try {
        $null = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/ready' -TimeoutSec 10
    } catch {
        Fail 'API is not ready on :8000; start it with .\scripts\run.ps1'
    }

    [System.IO.Directory]::CreateDirectory($RunDir) | Out-Null
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/openapi.json' -OutFile $SpecPath -TimeoutSec 30
    } catch {
        Fail 'could not download /openapi.json from the running API'
    }

    # The spec drives coverage; the base URL gives the agent a host to attack.
    $strixArgs += @('--target', $SpecPath, '--target', 'http://127.0.0.1:8000')

    if ($env:STRIX_TEST_EMAIL -and $env:STRIX_TEST_PASSWORD) {
        $instruction = "Grey-box testing. Sign in with POST /v1/auth/login using email $($env:STRIX_TEST_EMAIL) and password $($env:STRIX_TEST_PASSWORD), then use the returned bearer token for the authenticated endpoints. Stay inside localhost and do not attack external hosts."
    } else {
        $instruction = 'Stay inside localhost and do not attack external hosts. Register a disposable account through /v1/auth/signup to reach authenticated endpoints.'
    }
    $strixArgs += @('--instruction', $instruction)
} else {
    Write-Step 'Preparing an isolated worktree at HEAD'
    $gitCmd = Get-Command git -ErrorAction SilentlyContinue
    if (-not $gitCmd) {
        Fail 'git is not installed or not on PATH'
    }

    $GitExe = if ($gitCmd.Source) { $gitCmd.Source } else { $gitCmd.Path }

    if (Test-Path $Worktree) {
        & $GitExe -C $Root worktree remove --force $Worktree *> $null
        if ($LASTEXITCODE -ne 0) {
            Remove-Item -Recurse -Force $Worktree
        }
    }
    & $GitExe -C $Root worktree prune *> $null
    if (Test-Path $Worktree) {
        Remove-Item -Recurse -Force $Worktree
    }

    & $GitExe -C $Root worktree add --detach $Worktree HEAD *> $null
    if ($LASTEXITCODE -ne 0) {
        Fail 'could not create the scan worktree at HEAD'
    }
    $worktreeCreated = $true

    & $GitExe -C $Root diff --quiet 2>$null
    $unstaged = $LASTEXITCODE -ne 0
    & $GitExe -C $Root diff --cached --quiet 2>$null
    $staged = $LASTEXITCODE -ne 0
    if ($unstaged -or $staged) {
        Write-Warn 'uncommitted changes are not part of the scan; the worktree is at HEAD'
    }

    $strixArgs += @('--target', $Worktree)
}

$strixArgs += @(
    '--scan-mode', $ScanMode,
    '--scope-mode', 'full',
    '--max-budget', $Budget,
    '--max-turns', '300'
)

$exitCode = 0
try {
    Write-Step "Running Strix ($Mode | $ScanMode | budget `$$Budget)"
    & $StrixExe @strixArgs
    $exitCode = $LASTEXITCODE
} finally {
    if ($worktreeCreated -and $env:SF_STRIX_KEEP -ne '1') {
        & $GitExe -C $Root worktree remove --force $Worktree *> $null
        if ($LASTEXITCODE -ne 0 -and (Test-Path $Worktree)) {
            Remove-Item -Recurse -Force $Worktree
        }
    }
}

if ($exitCode -eq 1) {
    [Console]::Error.WriteLine('error: Strix failed before finishing; see the log above')
    exit 1
}

Write-Step "Done (exit $exitCode)"
Write-Host "Reports: $LogDir"
if ($Mode.ToLowerInvariant() -eq 'code' -and $env:SF_STRIX_KEEP -eq '1') {
    Write-Host "Worktree kept for review: $Worktree"
}
Write-Host 'Open the dashboard with: strix view'
if ($exitCode -eq 2) {
    Write-Host ''
    Write-Host 'Findings were reported. Triage them before treating any of them as real.'
}

exit $exitCode
