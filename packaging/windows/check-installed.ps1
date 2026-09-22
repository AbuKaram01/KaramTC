# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# What a user's machine has to look like after the installer ran (karamtc-<version>-windows-setup.exe): used by the
# manual CI job "windows-installer-run", and handy after a trial installation in a virtual machine:
#
#     powershell -ExecutionPolicy Bypass -File packaging\windows\check-installed.ps1 [-App <installation folder>]
#
# It checks that the GTK runtime is the one the installer carried (and that no second copy was downloaded), that the
# Python environment exists, that its libraries came from the wheelhouse inside the installer (nothing downloaded, no
# compiler), that GTK and libadwaita load from the runtime folder without being told where it is, that the program
# finds the Tesseract that came with the installer, and that the application stays up for a few seconds the way the
# Start menu entry starts it. With -ExpectBundledPython it also checks that the Python itself came from the python.org
# installer inside the installer (use it where no Python is installed yet).

param(
    [string]$App = (Join-Path $env:LOCALAPPDATA 'Programs\KaramTC'),
    [int]$SecondsToRun = 15,
    [switch]$ExpectBundledPython
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$AppId = 'io.github.AbuKaram01.KaramTC'
$DataRoot = Join-Path $env:LOCALAPPDATA $AppId

function Ok([string]$Text) { Write-Host "OK  $Text" -ForegroundColor Green }

# 1. The runtime the installer carried is beside the application.
$gtk = Join-Path $App 'gtk'
foreach ($needed in 'bin', 'lib\girepository-1.0\Gtk-4.0.typelib', 'lib\girepository-1.0\Adw-1.typelib', 'wheels', 'gvsbuild-release.txt') {
    if (-not (Test-Path (Join-Path $gtk $needed))) { throw "The installer did not put $needed in $gtk." }
}
Get-Content (Join-Path $gtk 'gvsbuild-release.txt') | ForEach-Object { Write-Host "    $_" }
Ok "GTK is in $gtk"

# 2. Nothing was downloaded to the place where the install script puts a runtime of its own.
$downloaded = Join-Path $DataRoot 'gtk'
if (Test-Path $downloaded) { throw "GTK was downloaded into $downloaded although the installer carries it." }
Ok 'no second copy of GTK was downloaded'

# 3. The install script ran to the end, and said that it used the runtime that came with the installer.
$python = Join-Path $App '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "The Python environment was not created in $App\.venv: the install script did not finish." }
Ok 'the Python environment exists'
$installLog = Join-Path $DataRoot 'install.log'
if (-not (Test-Path $installLog)) { throw "The install script left no log at $installLog." }
$logText = Get-Content $installLog -Raw
if ($logText -notmatch 'GTK 4 and libadwaita come with the installer') {
    throw "The install script did not use the GTK runtime that came with the installer; see $installLog."
}
Ok 'the install script used the GTK runtime that came with the installer'

# 3b. What the install script did about Python and its libraries, from the log it keeps. The installer carries the
# libraries (a wheelhouse), so none may have been downloaded or compiled, and Python itself must not have needed winget.
$wheelhouse = Join-Path $App 'wheelhouse'
foreach ($library in 'pymupdf', 'pillow', 'faster_whisper', 'ctranslate2', 'av') {
    if (-not (@(Get-ChildItem $wheelhouse -Filter '*.whl' -ErrorAction SilentlyContinue | Where-Object { $_.Name.ToLower().StartsWith("$library-") }))) {
        throw "The installer did not put the Python libraries (a wheelhouse with $library) in $wheelhouse."
    }
}
Ok "the Python libraries are in $wheelhouse"
if ($logText -notmatch 'Python libraries installed from the wheelhouse') { throw "The libraries were not installed from the wheelhouse; see $installLog." }
foreach ($forbidden in 'downloading them instead', 'Installing Python \S+ with winget') {
    if ($logText -match $forbidden) { throw "The installation used the internet where it should not have ('$forbidden'); see $installLog." }
}
Ok 'the libraries were installed from the wheelhouse, with nothing downloaded'
if ($ExpectBundledPython) {
    if ($logText -notmatch 'installer that came with KaramTC') { throw "Python was not installed from the installer that came with KaramTC; see $installLog." }
    $venvHome = (Get-Content (Join-Path $App '.venv\pyvenv.cfg') | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1)
    if (-not $venvHome -or $venvHome -notmatch 'Programs\\Python\\Python\d+') { throw "The environment was not made from the Python that the installer installed ($venvHome)." }
    Ok "Python came from the installer inside KaramTC ($($venvHome.Trim()))"
}

# 4. GTK loads from that folder, with nothing telling the application where it is.
Remove-Item Env:KARAMTC_GTK_DIR -ErrorAction SilentlyContinue
$probe = Join-Path ([IO.Path]::GetTempPath()) 'karamtc-check-installed.py'
Set-Content -LiteralPath $probe -Encoding UTF8 -Value @'
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "src"))
import winsupport                       # what main.py does before it imports GTK

found = winsupport.prepare_runtime()
print("runtime found:", found)
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

print("GTK %d.%d, libadwaita %d.%d" % (Gtk.get_major_version(), Gtk.get_minor_version(), Adw.get_major_version(), Adw.get_minor_version()))
beside = Path(sys.prefix).parent / "gtk"
assert found is not None and Path(found).resolve() == beside.resolve(), f"expected the runtime beside the application: {beside}"
'@
& $python $probe $App
if ($LASTEXITCODE -ne 0) { throw "GTK did not load from the installer's folder (exit code $LASTEXITCODE)." }
Ok 'GTK and libadwaita load from the installer''s folder'

# 4b. The program finds the Tesseract that came with the installer, from a console program (python.exe) and from one
# that has no console, as the Start menu entry runs it (pythonw.exe: where a program started without a window of its own
# behaves differently).
$bundledTesseract = Join-Path $App 'tesseract\tesseract.exe'
if (Test-Path -LiteralPath $bundledTesseract) {
    $engineProbe = Join-Path ([IO.Path]::GetTempPath()) 'karamtc-check-engine.py'
    Set-Content -LiteralPath $engineProbe -Encoding UTF8 -Value @'
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "src"))
from providers import tesseract
from providers.tesseract import program

found = program.find_tesseract()
version = None
if found:
    run = subprocess.run([program.program(), "--version"], capture_output=True, text=True, timeout=60,
                         creationflags=0x08000000)
    version = (run.stdout or run.stderr).splitlines()[0] if run.returncode == 0 else None
answer = {"found": found, "installed": tesseract.is_installed(), "version": version}
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(answer, handle)
'@
    foreach ($interpreter in 'python.exe', 'pythonw.exe') {
        $answerFile = Join-Path ([IO.Path]::GetTempPath()) "karamtc-engine-$interpreter.json"
        Remove-Item -LiteralPath $answerFile -ErrorAction SilentlyContinue
        $started = Start-Process -FilePath (Join-Path $App ".venv\Scripts\$interpreter") -ArgumentList "`"$engineProbe`"", "`"$App`"", "`"$answerFile`"" `
                                 -WorkingDirectory $App -WindowStyle Hidden -PassThru
        # pythonw.exe hands over to the real interpreter and may end before it does: wait for the answer itself.
        $deadline = (Get-Date).AddSeconds(120)
        while (-not (Test-Path -LiteralPath $answerFile) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
        if (-not (Test-Path -LiteralPath $answerFile)) { throw "$interpreter gave no answer about Tesseract within two minutes." }
        Start-Sleep -Milliseconds 300
        $engine = Get-Content -LiteralPath $answerFile -Raw | ConvertFrom-Json
        Write-Host "    $interpreter asked: found=$($engine.found) installed=$($engine.installed) version=$($engine.version)"
        if (-not $engine.found -or ((Resolve-Path -LiteralPath $engine.found).Path -ne (Resolve-Path -LiteralPath $bundledTesseract).Path)) {
            throw "The installed program ($interpreter) does not find the Tesseract that came with the installer ($bundledTesseract); it found '$($engine.found)'."
        }
        if (-not $engine.installed) { throw "The installed program ($interpreter) says that Tesseract is not installed." }
        if (-not $engine.version) { throw "The installed program ($interpreter) found Tesseract but cannot run it." }
    }
    Ok 'the program finds the Tesseract that came with the installer and runs it (with and without a console)'
} else {
    Write-Host 'NOTE the installer carries no Tesseract; whether the program finds one was not checked.' -ForegroundColor Yellow
}

# 5. The application starts and keeps running.
$pythonw = Join-Path $App '.venv\Scripts\pythonw.exe'
$process = Start-Process -FilePath $pythonw -ArgumentList ('"' + (Join-Path $App 'src\main.py') + '"') -WorkingDirectory $App -PassThru
Start-Sleep -Seconds $SecondsToRun
$exited = $process.HasExited
# pythonw starts the real interpreter as a child. taskkill fails when part of that tree is already gone, and a script
# that ends right after it would then exit with taskkill's code: so it is run by cmd and its code forgotten.
if (-not $exited) { cmd /c "taskkill /PID $($process.Id) /T /F >nul 2>&1"; $global:LASTEXITCODE = 0 }
$log = Join-Path $DataRoot 'karamtc.log'
if (Test-Path $log) { Write-Host '--- karamtc.log'; Get-Content $log }
if ($exited) { throw "The application exited early with code $($process.ExitCode)." }
Ok "the application was still running after $SecondsToRun seconds"
