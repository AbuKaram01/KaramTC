# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# A portable copy of Tesseract OCR for Windows: no installer is run, no administrator rights are needed, and nothing
# is written outside the target folder.
#
# It takes the official UB Mannheim Windows installer (one pinned version, checked against the SHA256 published in
# the winget manifest), unpacks it with 7-Zip instead of running it, and keeps only what tesseract.exe needs: the
# program, the libraries it loads (this is the MinGW build, so no Visual C++ runtime is needed), the English and
# orientation data, its configuration files, and the license notices (doc\). About 130 MB on disk.
#
# Dot-source this file, then:
#
#     Get-PortableTesseract -Target <folder>        # $true when <folder>\tesseract.exe is ready, else $false
#
# It never throws; it says why on the console when it returns $false.

$script:TesseractVersion = '5.4.0.20240606'
$script:TesseractUrl     = "https://github.com/UB-Mannheim/tesseract/releases/download/v$($script:TesseractVersion)/tesseract-ocr-w64-setup-$($script:TesseractVersion).exe"
$script:TesseractSha256  = 'C885FFF6998E0608BA4BB8AB51436E1C6775C2BAFC2559A19B423E18678B60C9'
$script:TesseractFiles   = @(
    'tesseract.exe', 'libtesseract-5.dll', 'libleptonica-6.dll',
    'libarchive-13.dll', 'libb2-1.dll', 'libbz2-1.dll', 'libcrypto-3-x64.dll', 'libdeflate.dll', 'libexpat-1.dll',
    'libgcc_s_seh-1.dll', 'libgif-7.dll', 'libiconv-2.dll', 'libjbig-0.dll', 'libjpeg-8.dll', 'libLerc.dll',
    'liblz4.dll', 'liblzma-5.dll', 'libopenjp2-7.dll', 'libpng16-16.dll', 'libsharpyuv-0.dll', 'libstdc++-6.dll',
    'libtiff-6.dll', 'libwebp-7.dll', 'libwebpmux-3.dll', 'libwinpthread-1.dll', 'libzstd.dll', 'zlib1.dll'
)

function Find-SevenZip {
    foreach ($name in '7z.exe', '7zz.exe', '7z') {
        $found = Get-Command $name -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    foreach ($folder in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $(if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Programs' }))) {
        if ($folder) {
            $candidate = Join-Path $folder '7-Zip\7z.exe'
            if (Test-Path $candidate) { return $candidate }
        }
    }
    return $null
}

# True when the program in $Folder starts and reports its version.
function Test-PortableTesseract([string]$Folder) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'      # Windows PowerShell 5.1 turns native stderr into errors under 'Stop'.
    try {
        $output = & (Join-Path $Folder 'tesseract.exe') --version 2>&1
        return ($LASTEXITCODE -eq 0) -and (($output | Out-String) -match 'tesseract')
    } catch { return $false } finally { $ErrorActionPreference = $saved }
}

function Get-PortableTesseract {
    param([Parameter(Mandatory)][string]$Target)

    if (Test-Path (Join-Path $Target 'tesseract.exe')) { return $true }
    $work = Join-Path ([IO.Path]::GetTempPath()) ('tesseract-portable-' + [guid]::NewGuid().ToString('N'))
    try {
        $sevenZip = Find-SevenZip
        if (-not $sevenZip) {
            Write-Host '!!  7-Zip was not found, so a portable Tesseract cannot be unpacked (winget install 7zip.7zip).' -ForegroundColor Yellow
            return $false
        }
        New-Item -ItemType Directory -Force -Path $work | Out-Null
        $installer = Join-Path $work 'tesseract-setup.exe'
        Write-Host "==> Downloading Tesseract $($script:TesseractVersion) (about 50 MB)..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $script:TesseractUrl -OutFile $installer -UseBasicParsing
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash
        if ($hash -ne $script:TesseractSha256) { throw "The download does not match the published SHA256 ($hash)." }

        Write-Host '==> Unpacking Tesseract...' -ForegroundColor Cyan
        $unpacked = Join-Path $work 'unpacked'
        & $sevenZip x -y "-o$unpacked" $installer | Out-Null
        if ($LASTEXITCODE -gt 1) { throw "7-Zip failed with exit code $LASTEXITCODE." }      # 1 means warnings only.

        # Built beside the target and moved into place at the end, so a failure never leaves a half-made folder.
        $staging = $Target + '.partial'
        if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
        $data = Join-Path $staging 'tessdata'
        New-Item -ItemType Directory -Force -Path $data | Out-Null
        foreach ($name in $script:TesseractFiles) {
            Copy-Item -LiteralPath (Join-Path $unpacked $name) -Destination $staging -ErrorAction Stop
        }
        foreach ($name in 'eng.traineddata', 'osd.traineddata', 'pdf.ttf') {
            Copy-Item -LiteralPath (Join-Path (Join-Path $unpacked 'tessdata') $name) -Destination $data -ErrorAction Stop
        }
        foreach ($name in 'configs', 'tessconfigs') {
            Copy-Item -LiteralPath (Join-Path (Join-Path $unpacked 'tessdata') $name) -Destination $data -Recurse -ErrorAction Stop
        }
        # Tesseract is Apache-2.0 licensed and ships its libraries' notices: they travel with the copy.
        Copy-Item -LiteralPath (Join-Path $unpacked 'doc') -Destination (Join-Path $staging 'doc') -Recurse -ErrorAction Stop
        if (-not (Test-PortableTesseract $staging)) { throw 'The unpacked tesseract.exe does not start.' }

        if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
        Move-Item -LiteralPath $staging -Destination $Target
        return $true
    } catch {
        Write-Host "!!  A portable Tesseract could not be prepared: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    } finally {
        if (Test-Path $work) { Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
