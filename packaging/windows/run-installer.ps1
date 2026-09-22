# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Runs the installer that packaging\build-windows.ps1 built, silently, the way a user's click would, for the manual CI
# job "windows-installer-run". It gives up after a while instead of hanging, and shows what the install script
# printed (the installer has it written to %LOCALAPPDATA%\io.github.AbuKaram01.KaramTC\install.log) whether the run worked or not.
#
#     powershell -ExecutionPolicy Bypass -File packaging\windows\run-installer.ps1 [-Label first] [-TimeoutMinutes 25]

param(
    [string]$Label = 'first',
    [int]$TimeoutMinutes = 25
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$setup = Get-ChildItem (Join-Path $PSScriptRoot '..\dist\*.exe') | Select-Object -First 1
if (-not $setup) { throw 'No installer was built (packaging\dist\*.exe).' }
$innoLog = Join-Path ([IO.Path]::GetTempPath()) "karamtc-setup-$Label.log"
$scriptLog = Join-Path $env:LOCALAPPDATA 'io.github.AbuKaram01.KaramTC\install.log'

Write-Host "Running $($setup.Name) ($Label run)..."
try {
    $process = Start-Process -FilePath $setup.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=$innoLog" -PassThru
    if (-not $process.WaitForExit($TimeoutMinutes * 60 * 1000)) {
        & taskkill /PID $process.Id /T /F | Out-Null
        throw "The installer was still running after $TimeoutMinutes minutes."
    }
    if ($process.ExitCode -ne 0) { throw "The installer exited with code $($process.ExitCode)." }
    Write-Host "OK  The installer finished ($Label run)." -ForegroundColor Green
} finally {
    if (Test-Path $innoLog) { Write-Host '--- Inno Setup log (last lines)'; Get-Content $innoLog | Select-Object -Last 30 }
    if (Test-Path $scriptLog) { Write-Host '--- what the install script printed (last lines)'; Get-Content $scriptLog | Select-Object -Last 120 }
}
