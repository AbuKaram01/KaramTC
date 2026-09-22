# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# The GTK 4 + libadwaita runtime for Windows (the prebuilt gvsbuild release), prepared as a folder that can travel
# inside the installer. Nothing is installed and nothing is written outside the target folder.
#
# Dot-source this file, then:
#
#     Get-PortableGtk -Target <folder> [-Tag <tag>|latest] [-Sha256 <hash>] [-ZipPath <zip>]
#                                                  # $true when <folder> is a complete runtime, else $false
#     Test-GtkRuntime <folder>                     # is it a complete runtime?
#     Resolve-GtkChoice -Explicit <dir> -ProjectRoot <dir> -DefaultDir <dir>
#                                                  # which runtime install-windows.ps1 should use
#
# Get-PortableGtk never throws; it says why on the console when it returns $false.
#
# Which gvsbuild release: the one named below unless -Tag says otherwise ("latest" asks GitHub for the newest). It is not
# "the newest" by default because the release decides which Python the PyGObject and pycairo wheels in it are for, and
# the application's other libraries (PyMuPDF, faster-whisper, PyAV) have to exist for that Python: gvsbuild
# 2026.10.0 moved its wheels to Python 3.15 while 2026.8.0 has them for 3.14. When you move to a newer release, change the
# tag here and the Python version of the jobs in .github/workflows/ci.yml together, and run the manual jobs.
#
# The download is checked against the SHA256 given with -Sha256, or else against the digest that GitHub publishes for
# that release file when it publishes one. The hash that was actually used is printed and kept in
# <folder>\gvsbuild-release.txt, so a release build can pin it with -Sha256.

$script:GtkDefaultTag = '2026.8.0'

# A runtime has the DLLs, the GTK and libadwaita typelibs, and libadwaita itself (the DLL is adwaita-1-0.dll, not
# libadwaita-...).
function Test-GtkRuntime([string]$Folder) {
    if (-not $Folder) { return $false }
    return (Test-Path (Join-Path $Folder 'bin')) -and
           (Test-Path (Join-Path $Folder 'lib\girepository-1.0\Gtk-4.0.typelib')) -and
           (Test-Path (Join-Path $Folder 'lib\girepository-1.0\Adw-1.typelib')) -and
           [bool](Get-ChildItem (Join-Path $Folder 'bin') -Filter '*adwaita-1-*.dll' -ErrorAction SilentlyContinue)
}

# Which runtime to use: one named with -GtkDir wins; then the copy that came inside the installer
# (<application folder>\gtk, which the application finds by itself); then the default folder, where one is downloaded
# when it is missing. Dir is the folder; Custom says it has to be told to the application (KARAMTC_GTK_DIR).
function Resolve-GtkChoice([string]$Explicit, [string]$ProjectRoot, [string]$DefaultDir) {
    if ($Explicit) {
        $folder = (Resolve-Path $Explicit).Path
        return [pscustomobject]@{ Dir = $folder; Custom = ($folder -ne $DefaultDir); Bundled = $false }
    }
    $bundled = Join-Path $ProjectRoot 'gtk'
    if (Test-GtkRuntime $bundled) {
        return [pscustomobject]@{ Dir = $bundled; Custom = $false; Bundled = $true }
    }
    return [pscustomobject]@{ Dir = $DefaultDir; Custom = $false; Bundled = $false }
}

# The tag of a gvsbuild release: the one given, the tested one when none is, or the newest for "latest". The "latest"
# redirect is tried first because the GitHub API allows only 60 anonymous requests per hour per address, which a shared
# connection can exhaust.
function Resolve-GtkTag([string]$Tag) {
    if (-not $Tag) { return $script:GtkDefaultTag }
    if ($Tag -ne 'latest') { return $Tag }
    try {
        $request = [Net.HttpWebRequest]::Create('https://github.com/wingtk/gvsbuild/releases/latest')
        $request.Method = 'HEAD'
        $request.AllowAutoRedirect = $false
        $request.UserAgent = 'karamtc-build'
        $response = $request.GetResponse()
        $location = [string]$response.Headers['Location']
        $response.Close()
        if ($location -match '/tag/([^/]+)$') { return $Matches[1] }
    } catch { }
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/wingtk/gvsbuild/releases/latest' -Headers (Get-GitHubHeaders)
    return [string]$release.tag_name
}

function Get-GitHubHeaders {
    $headers = @{ 'User-Agent' = 'karamtc-build' }
    if ($env:GITHUB_TOKEN) { $headers['Authorization'] = "Bearer $($env:GITHUB_TOKEN)" }      # Lifts the API rate limit.
    return $headers
}

# The SHA256 that GitHub publishes for a release file, or $null (older files have none, and the API may be out of reach).
function Get-GtkPublishedDigest([string]$Tag, [string]$AssetName) {
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/wingtk/gvsbuild/releases/tags/$Tag" -Headers (Get-GitHubHeaders)
        $asset = $release.assets | Where-Object { $_.name -eq $AssetName } | Select-Object -First 1
        if ($asset -and ($asset.PSObject.Properties.Name -contains 'digest') -and ([string]$asset.digest -match '^sha256:([0-9a-fA-F]{64})$')) {
            return $Matches[1].ToUpper()
        }
    } catch { }
    return $null
}

function Get-PortableGtk {
    param(
        [Parameter(Mandatory)][string]$Target,
        [string]$Tag = '',
        [string]$Sha256 = '',
        # A GTK4_Gvsbuild_*_x64.zip that is already on this machine: nothing is downloaded (offline builds).
        [string]$ZipPath = ''
    )

    if (Test-GtkRuntime $Target) { return $true }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('gtk-portable-' + [guid]::NewGuid().ToString('N'))
    try {
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
        New-Item -ItemType Directory -Force -Path $work | Out-Null

        if ($ZipPath) {
            if (-not (Test-Path -LiteralPath $ZipPath)) { throw "$ZipPath does not exist." }
            $zip = (Resolve-Path -LiteralPath $ZipPath).Path
            $release = '(local file) ' + (Split-Path -Leaf $zip)
            $expected = $Sha256.ToUpper()
        } else {
            $resolved = Resolve-GtkTag $Tag
            $asset = "GTK4_Gvsbuild_${resolved}_x64.zip"
            $zip = Join-Path $work $asset
            Write-Host "==> Downloading GTK 4 + libadwaita (gvsbuild $resolved)..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri "https://github.com/wingtk/gvsbuild/releases/download/$resolved/$asset" -OutFile $zip -UseBasicParsing
            $release = $resolved
            $expected = if ($Sha256) { $Sha256.ToUpper() } else { [string](Get-GtkPublishedDigest $resolved $asset) }
        }

        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash
        if ($expected -and ($hash -ne $expected)) { throw "The file does not match the expected SHA256 (got $hash, expected $expected)." }
        if ($expected) { Write-Host "OK  GTK zip SHA256 $hash matches." -ForegroundColor Green }
        else { Write-Host "!!  No SHA256 to check the GTK zip against (none given, none published). Its SHA256 is $hash." -ForegroundColor Yellow }

        Write-Host '==> Unpacking GTK...' -ForegroundColor Cyan
        $unpacked = Join-Path $work 'unpacked'
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($zip, $unpacked)

        # The archive may hold the runtime at its top level or inside one folder.
        $root = $unpacked
        if (-not (Test-Path (Join-Path $root 'bin'))) {
            $inner = Get-ChildItem $unpacked -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'bin') } | Select-Object -First 1
            if ($inner) { $root = $inner.FullName }
        }

        # Built beside the target and moved into place at the end, so a failure never leaves a half-made folder.
        $staging = $Target + '.partial'
        if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $staging) | Out-Null
        Move-Item -LiteralPath $root -Destination $staging
        if (-not (Test-GtkRuntime $staging)) { throw 'The archive is not a complete GTK 4 + libadwaita runtime (it needs bin, the Gtk-4.0 and Adw-1 typelibs, and adwaita-1-*.dll).' }

        # What is in the folder, for whoever opens it later (and for a release build to pin).
        Set-Content -LiteralPath (Join-Path $staging 'gvsbuild-release.txt') -Encoding UTF8 -Value @(
            "gvsbuild release: $release",
            "SHA256 of the zip: $hash",
            "Prepared: $([DateTime]::UtcNow.ToString('yyyy-MM-dd HH:mm')) UTC"
        )

        if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
        Move-Item -LiteralPath $staging -Destination $Target
        return $true
    } catch {
        Write-Host "!!  The GTK runtime could not be prepared: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    } finally {
        if (Test-Path $work) { Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue }
        if ($Target -and (Test-Path ($Target + '.partial'))) { Remove-Item ($Target + '.partial') -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
