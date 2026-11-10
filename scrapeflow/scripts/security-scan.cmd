@echo off
rem Windows Command Prompt launcher for scripts\security-scan.ps1.
rem Use this when PowerShell's execution policy blocks .ps1 files.
setlocal
set "RUNNER=%~dp0security-scan.ps1"

where pwsh.exe >nul 2>nul
if errorlevel 1 (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%RUNNER%" %*
) else (
    pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%RUNNER%" %*
)

exit /b %ERRORLEVEL%
