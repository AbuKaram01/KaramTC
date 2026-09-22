# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Removes what scripts\install-windows.ps1 created. Your downloaded models, OCR language data and settings are kept
# unless you ask for them to be deleted:
#
#     powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1 [-RemoveGtk] [-RemoveData]

[CmdletBinding()]
param(
    # Also delete the GTK runtime that a script downloaded (%LOCALAPPDATA%\io.github.AbuKaram01.KaramTC\gtk).
    [switch]$RemoveGtk,
    # Also delete downloaded models, OCR language data and settings. Cannot be undone.
    [switch]$RemoveData,
    [switch]$Force
)

Set-StrictMode -Version 2.0

# This script is for Windows only; say so clearly instead of failing on a missing %LOCALAPPDATA%.
if ($env:OS -ne 'Windows_NT') {
    Write-Host 'ERR This script is for Windows. On Linux use scripts/install-debian.sh or scripts/install-arch.sh.' -ForegroundColor Red
    exit 1
}
$ErrorActionPreference = 'Stop'

$AppId       = 'io.github.AbuKaram01.KaramTC'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DataRoot    = Join-Path $env:LOCALAPPDATA $AppId
$ConfigRoot  = Join-Path $env:APPDATA $AppId

function Info($Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Remove-IfPresent([string]$Path) {
    if (Test-Path $Path) { Remove-Item $Path -Recurse -Force; Info "Removed $Path" }
}

if ($RemoveData -and -not $Force) {
    $answer = Read-Host "This deletes your downloaded models, OCR language data and settings. Type YES to continue"
    if ($answer -ne 'YES') { Write-Host 'Nothing was deleted.'; exit 1 }
}

Remove-IfPresent (Join-Path ([Environment]::GetFolderPath('Programs')) 'KaramTC.lnk')
Remove-IfPresent (Join-Path $ProjectRoot '.venv')
Remove-IfPresent (Join-Path $DataRoot 'tesseract')      # The portable copy the installer fetched; not your data.
$carriedGtk = Join-Path $ProjectRoot 'gtk'
if (Test-Path (Join-Path $carriedGtk 'gvsbuild-release.txt')) { Remove-IfPresent $carriedGtk }      # The runtime the installer carried.
[Environment]::SetEnvironmentVariable('KARAMTC_GTK_DIR', $null, 'User')

if ($RemoveGtk) { Remove-IfPresent (Join-Path $DataRoot 'gtk') }
if ($RemoveData) {
    Remove-IfPresent $ConfigRoot
    Get-ChildItem $DataRoot -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne 'gtk' -or $RemoveGtk } | ForEach-Object { Remove-IfPresent $_.FullName }
    if ((Test-Path $DataRoot) -and -not (Get-ChildItem $DataRoot -Force)) { Remove-Item $DataRoot -Force }
}

Write-Host 'Done.'
if (-not $RemoveData) { Write-Host "Your data is still in $DataRoot and $ConfigRoot (use -RemoveData to delete it)." }
