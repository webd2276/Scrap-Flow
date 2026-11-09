#requires -Version 5.1
<#
.SYNOPSIS
    Start or control the complete ScrapeFlow stack on Windows.

.DESCRIPTION
    Builds and starts the Docker Compose stack, waits for readiness, and exposes
    the same maintenance commands as the Linux/macOS runner (scripts/run.sh).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1

.EXAMPLE
    .\scripts\run.ps1 status

.EXAMPLE
    .\scripts\run.ps1 fix-db-password
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Command = 'start',

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

$EnvFile = if ($env:SF_ENV_FILE) {
    [System.IO.Path]::GetFullPath($env:SF_ENV_FILE)
} else {
    Join-Path $Root '.env'
}

$S3Mode = if ($env:SF_S3_MODE) { $env:SF_S3_MODE.ToLowerInvariant() } else { 'auto' }
$script:EffectiveS3Mode = $S3Mode

$HealthTimeout = 240
if ($env:SF_HEALTH_TIMEOUT) {
    $parsed = 0
    if (-not [int]::TryParse($env:SF_HEALTH_TIMEOUT, [ref]$parsed) -or $parsed -lt 10) {
        [Console]::Error.WriteLine('error: SF_HEALTH_TIMEOUT must be an integer >= 10')
        exit 1
    }
    $HealthTimeout = $parsed
}

$MinioImage = if ($env:MINIO_IMAGE) {
    $env:MINIO_IMAGE
} else {
    'quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z'
}

$RunDir = Join-Path $Root '.run'
$S3MockOverride = Join-Path $RunDir 's3mock-override.yml'
$script:ExtraFiles = @()
$script:LastComposeExitCode = 0

function Write-Step {
    param([string]$Message)
    Write-Host ''
    Write-Host "==> $Message"
}

function Write-Warn {
    param([string]$Message)
    [Console]::Error.WriteLine("warning: $Message")
}

function Die {
    param([string]$Message)
    [Console]::Error.WriteLine("error: $Message")
    exit 1
}

function Show-Usage {
    Write-Host @'
Start (or control) the complete ScrapeFlow stack on Windows.

Usage:
  .\scripts\run.ps1                    build + start, wait for readiness
  .\scripts\run.ps1 logs               follow API/worker/beat/web logs
  .\scripts\run.ps1 status             container status
  .\scripts\run.ps1 seed               create demo org/user/API key (prints once)
  .\scripts\run.ps1 fix-db-password    sync the Postgres role to .env, keep data
  .\scripts\run.ps1 stop               stop containers, keep data volumes
  .\scripts\run.ps1 reset              stop containers and delete data volumes

Environment:
  $env:SF_S3_MODE = "auto"|"minio"|"s3mock"   default: auto
  $env:SF_ENV_FILE = "C:\path\.env"           default: <repo>\.env
  $env:SF_HEALTH_TIMEOUT = "240"              seconds to wait for /ready
  $env:MINIO_IMAGE = "..."                    image tried in auto/minio mode

If PowerShell blocks the script, run it with:
  powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1
or use the Command Prompt launcher:
  scripts\run.cmd
'@
}

function Write-Utf8NoBom {
    param(
        [string]$Path,
        [string]$Content
    )
    $parent = Split-Path -Parent $Path
    if ($parent) {
        [System.IO.Directory]::CreateDirectory($parent) | Out-Null
    }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Protect-SecretFile {
    param([string]$Path)
    $onWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
    if ($onWindows) {
        try {
            $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            & icacls $Path /inheritance:r /grant:r "$($identity):(F)" | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "could not restrict NTFS permissions on $Path"
            }
        } catch {
            Write-Warn "could not restrict NTFS permissions on $Path"
        }
        return
    }

    try {
        & chmod 600 $Path
    } catch {
        Write-Warn "could not set mode 600 on $Path"
    }
}

function New-RandomToken {
    param([int]$Bytes)
    $buffer = New-Object 'byte[]' $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($buffer)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-EnvFile {
    if (Test-Path -LiteralPath $EnvFile) {
        return
    }

    $example = Join-Path $Root '.env.example'
    if (-not (Test-Path -LiteralPath $example -PathType Leaf)) {
        Die "missing template: $example"
    }

    Write-Step "Creating $EnvFile with random secrets"
    $dbPassword = New-RandomToken -Bytes 24
    $lines = New-Object System.Collections.Generic.List[string]

    foreach ($line in [System.IO.File]::ReadAllLines($example)) {
        $stripped = $line.Trim()
        if ($stripped.StartsWith('#') -or -not $stripped.Contains('=')) {
            $lines.Add($line)
            continue
        }

        $index = $line.IndexOf('=')
        $key = $line.Substring(0, $index)
        $value = $line.Substring($index + 1)

        # Order matters: the longer marker contains the shorter one.
        if ($value.Contains('CHANGE_ME_32_PLUS_RANDOM_CHARACTERS')) {
            $value = $value.Replace(
                'CHANGE_ME_32_PLUS_RANDOM_CHARACTERS',
                (New-RandomToken -Bytes 48)
            )
        }
        if ($value.Contains('CHANGE_ME')) {
            $value = $value.Replace('CHANGE_ME', $dbPassword)
        }
        $lines.Add("$key=$value")
    }

    Write-Utf8NoBom -Path $EnvFile -Content (($lines -join "`n") + "`n")
    Protect-SecretFile -Path $EnvFile
    Write-Step "Wrote $EnvFile; review it before starting compose"
}

function Read-EnvMap {
    $map = @{}
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        return $map
    }
    foreach ($line in [System.IO.File]::ReadAllLines($EnvFile)) {
        $stripped = $line.Trim()
        if ($stripped.Length -eq 0 -or $stripped.StartsWith('#') -or -not $stripped.Contains('=')) {
            continue
        }
        $index = $stripped.IndexOf('=')
        $name = $stripped.Substring(0, $index).Trim()
        $value = $stripped.Substring($index + 1).Trim()
        $map[$name] = $value
    }
    return $map
}

function Assert-EnvFile {
    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        Die "missing environment file: $EnvFile"
    }
}

function Get-ComposeArgumentList {
    param([string[]]$ComposeArgs)
    $arguments = @(
        'compose',
        '--project-directory', $Root,
        '-f', (Join-Path $Root 'docker-compose.yml')
    )
    foreach ($file in $script:ExtraFiles) {
        $arguments += @('-f', $file)
    }
    $arguments += @('--env-file', $EnvFile)
    if ($ComposeArgs) {
        $arguments += $ComposeArgs
    }
    return ,$arguments
}

function Invoke-DockerCompose {
    param(
        [string[]]$ComposeArgs,
        [bool]$AllowFailure,
        [bool]$HasInput,
        [string]$InputText
    )
    $arguments = Get-ComposeArgumentList -ComposeArgs $ComposeArgs
    if ($HasInput) {
        $previousEncoding = $OutputEncoding
        try {
            $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
            $InputText | & docker @arguments
        } finally {
            $OutputEncoding = $previousEncoding
        }
    } else {
        & docker @arguments
    }
    $script:LastComposeExitCode = $LASTEXITCODE
    if ($script:LastComposeExitCode -ne 0 -and -not $AllowFailure) {
        throw "docker compose failed with exit code $script:LastComposeExitCode"
    }
}

function Invoke-Compose {
    Invoke-DockerCompose -ComposeArgs @($args) -AllowFailure $false -HasInput $false -InputText ''
}

function Invoke-ComposeAllowFailure {
    Invoke-DockerCompose -ComposeArgs @($args) -AllowFailure $true -HasInput $false -InputText ''
}

function Invoke-ComposeWithInput {
    $inputText = [string]$args[0]
    $composeArgs = if ($args.Count -gt 1) {
        @($args[1..($args.Count - 1)])
    } else {
        @()
    }
    Invoke-DockerCompose -ComposeArgs $composeArgs -AllowFailure $false -HasInput $true -InputText $inputText
}

function Test-DockerPull {
    param(
        [string]$Image,
        [int]$TimeoutSeconds = 120
    )
    [System.IO.Directory]::CreateDirectory($RunDir) | Out-Null
    $stdout = Join-Path $RunDir 'docker-pull.out'
    $stderr = Join-Path $RunDir 'docker-pull.err'
    Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue

    $process = $null
    try {
        $process = Start-Process `
            -FilePath 'docker' `
            -ArgumentList @('pull', $Image) `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try {
                $process.Kill()
            } catch {
                Write-Verbose 'docker pull exited before the timeout kill'
            }
            $null = $process.WaitForExit(5000)
            return $false
        }
        return ($process.ExitCode -eq 0)
    } finally {
        Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue
    }
}

function Write-S3MockOverride {
    $content = @'
services:
  minio:
    image: adobe/s3mock:latest
    command: []
    environment:
      HTTP_PORT: "9000"
      COM_ADOBE_TESTING_S3MOCK_STORE_INITIAL_BUCKETS: scrapeflow
    healthcheck:
      test: ["CMD-SHELL", "exit 0"]
      interval: 2s
      timeout: 2s
      retries: 5
    ports:
      - "127.0.0.1:9000:9000"

  minio-init:
    command: ["python", "-c", "print('S3 mock bucket pre-created')"]
'@
    $content = $content.Replace("`r`n", "`n")
    Write-Utf8NoBom -Path $S3MockOverride -Content ($content + "`n")
}

function Select-S3 {
    switch ($S3Mode) {
        'minio' {
            $script:EffectiveS3Mode = 'minio'
            Write-Step "Using MinIO image: $MinioImage"
        }
        's3mock' {
            $script:EffectiveS3Mode = 's3mock'
            Write-Step 'Using adobe/s3mock for S3'
            Write-S3MockOverride
            $script:ExtraFiles += $S3MockOverride
        }
        'auto' {
            $null = & docker image inspect $MinioImage 2>$null
            if ($LASTEXITCODE -eq 0) {
                $script:EffectiveS3Mode = 'minio'
                Write-Step "Using local MinIO image: $MinioImage"
            } elseif (Test-DockerPull -Image $MinioImage -TimeoutSeconds 120) {
                $script:EffectiveS3Mode = 'minio'
                Write-Step "Pulled MinIO image: $MinioImage"
            } else {
                $script:EffectiveS3Mode = 's3mock'
                Write-Warn 'MinIO image is unavailable; falling back to adobe/s3mock.'
                Write-Warn 'Set SF_S3_MODE=minio to require real MinIO instead.'
                Write-S3MockOverride
                $script:ExtraFiles += $S3MockOverride
            }
        }
        default {
            Die "SF_S3_MODE must be auto, minio, or s3mock (got: $S3Mode)"
        }
    }
}

function Assert-Prerequisites {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Die 'docker is not installed or not on PATH'
    }

    $null = & docker info 2>$null
    if ($LASTEXITCODE -ne 0) {
        Die 'the Docker daemon is not running (start Docker Desktop)'
    }

    $null = & docker compose version 2>$null
    if ($LASTEXITCODE -ne 0) {
        Die 'Docker Compose v2 is required'
    }

    if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
        New-EnvFile
    }
    Assert-EnvFile
}

function Wait-ForApi {
    Write-Step "Waiting up to ${HealthTimeout}s for the API"
    $deadline = [DateTime]::UtcNow.AddSeconds($HealthTimeout)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -Uri 'http://127.0.0.1:8000/ready' `
                -UseBasicParsing `
                -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            Write-Verbose 'API is not ready yet'
        }
        Start-Sleep -Seconds 2
    }

    Invoke-ComposeAllowFailure ps
    Invoke-ComposeAllowFailure logs --tail=80 api migrate worker
    Die "API did not become ready within ${HealthTimeout}s"
}

function Wait-ForWeb {
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $response = Invoke-WebRequest `
                -Uri 'http://127.0.0.1:3000/login' `
                -UseBasicParsing `
                -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            Write-Verbose 'dashboard is not ready yet'
        }
        Start-Sleep -Seconds 2
    }
    Write-Warn 'dashboard is not answering on http://127.0.0.1:3000 yet'
}

function Start-Stack {
    Assert-Prerequisites
    Select-S3

    Write-Step 'Building and starting ScrapeFlow (first run can take several minutes)'
    Invoke-ComposeAllowFailure up -d --build
    if ($script:LastComposeExitCode -ne 0) {
        Invoke-ComposeAllowFailure logs --tail=40 migrate
        [Console]::Error.WriteLine(@'

Startup failed. If migrate reports "password authentication failed", the
PostgreSQL data volume was created with a different password than the current
.env. Repair it without deleting data:

  .\scripts\run.ps1 fix-db-password

Or delete local data and start clean:

  .\scripts\run.ps1 reset
'@)
        exit 1
    }

    Wait-ForApi
    Wait-ForWeb

    Invoke-Compose ps

    Write-Host @"

ScrapeFlow is running.

  API         http://127.0.0.1:8000
  API docs    http://127.0.0.1:8000/docs
  Dashboard   http://127.0.0.1:3000
  Metrics     http://127.0.0.1:8000/metrics

Useful commands:
  .\scripts\run.ps1 logs      follow logs
  .\scripts\run.ps1 seed      create demo user + API key
  .\scripts\run.ps1 stop      stop containers (data is kept)
  .\scripts\run.ps1 reset     stop and delete data volumes

S3 mode: $($script:EffectiveS3Mode)
"@
}

function Repair-DbPassword {
    Assert-Prerequisites

    $envMap = Read-EnvMap
    $user = $envMap['POSTGRES_USER']
    if ([string]::IsNullOrWhiteSpace($user)) {
        $user = 'scrapeflow'
    }

    Write-Step 'Starting PostgreSQL'
    Invoke-Compose up -d postgres

    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ($true) {
        Invoke-ComposeAllowFailure exec -T postgres pg_isready -U $user -d postgres | Out-Null
        if ($script:LastComposeExitCode -eq 0) {
            break
        }
        if ([DateTime]::UtcNow -ge $deadline) {
            Die 'PostgreSQL did not become ready'
        }
        Start-Sleep -Seconds 2
    }

    $databaseUrl = $envMap['DATABASE_URL']
    if ([string]::IsNullOrWhiteSpace($databaseUrl)) {
        Die "DATABASE_URL is missing from $EnvFile"
    }
    $match = [regex]::Match($databaseUrl, '^[^:]+://([^:]+):([^@]*)@')
    if (-not $match.Success) {
        Die 'DATABASE_URL is missing a user/password'
    }

    $dbUser = [System.Uri]::UnescapeDataString($match.Groups[1].Value)
    $password = [System.Uri]::UnescapeDataString($match.Groups[2].Value)
    $role = $dbUser.Replace('"', '""')
    $literal = $password.Replace("'", "''")
    $sql = "ALTER ROLE `"$role`" WITH PASSWORD '$literal';`n"
    $sql += "\echo role $dbUser now matches DATABASE_URL`n"

    [System.IO.Directory]::CreateDirectory($RunDir) | Out-Null
    $sqlFile = Join-Path $RunDir 'fix-db-password.sql'
    try {
        Write-Utf8NoBom -Path $sqlFile -Content $sql
        Protect-SecretFile -Path $sqlFile
        $sqlText = [System.IO.File]::ReadAllText($sqlFile)
        Invoke-ComposeWithInput $sqlText exec -T postgres psql -U $user -d postgres -v ON_ERROR_STOP=1
    } finally {
        Remove-Item -LiteralPath $sqlFile -Force -ErrorAction SilentlyContinue
    }
    Write-Step 'Postgres role password now matches DATABASE_URL'
}

try {
    if ($Help) {
        Show-Usage
        exit 0
    }

    switch ($Command.ToLowerInvariant()) {
        'start' {
            Start-Stack
        }
        'logs' {
            Assert-EnvFile
            Invoke-Compose logs -f --tail=100 api worker beat web egress-proxy
        }
        'status' {
            Assert-EnvFile
            Invoke-Compose ps
        }
        'ps' {
            Assert-EnvFile
            Invoke-Compose ps
        }
        'seed' {
            Assert-EnvFile
            Invoke-Compose exec api python -m scripts.seed
        }
        'fix-db-password' {
            Repair-DbPassword
        }
        'stop' {
            Assert-EnvFile
            Invoke-Compose down
        }
        'reset' {
            Assert-EnvFile
            Write-Step 'Stopping containers and deleting data volumes'
            Invoke-Compose down -v
        }
        'help' {
            Show-Usage
        }
        '-h' {
            Show-Usage
        }
        '--help' {
            Show-Usage
        }
        default {
            Show-Usage
            Die "unknown command: $Command"
        }
    }
} catch {
    [Console]::Error.WriteLine("error: $($_.Exception.Message)")
    exit 1
}
