# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# The Visual C++ runtime DLLs that the libraries of KaramTC import and that Windows does not have, collected so that
# packaging\build-windows.ps1 can put them inside the installer. A computer that never had the Visual C++
# Redistributable has no msvcp140.dll, and without it ctranslate2 and onnxruntime (faster-whisper, the Audio/Video tab)
# do not load; the installer then carries its own copies and the program loads them first (src\winsupport.py).
# packaging\windows\dlls.py says which DLLs the installed program needs from the machine.
#
# Dot-sourced by packaging\build-windows.ps1. Works in Windows PowerShell 5.1 and PowerShell 7.

$script:VcRuntimeProblem = ''

# What is copied: the C++ standard library (msvcp140.dll, msvcp140_1.dll, ...), the parallel runtime (concrt140.dll) and
# OpenMP (vcomp140.dll). Not vcruntime140.dll and vcruntime140_1.dll: Python's own installer puts them beside python.exe,
# and a second copy in another folder would be a second copy of the C runtime in one process.
$script:VcRuntimePatterns = @('msvcp140*.dll', 'concrt140.dll', 'vcomp140.dll')
# Without these the libraries do not load on a machine that lacks the Redistributable (what packaging\windows\dlls.py found).
$script:VcRuntimeRequired = @('msvcp140.dll', 'msvcp140_1.dll', 'vcomp140.dll')

function Join-Segments([string]$Base, [string[]]$Parts) {
    # Join-Path with several segments, written so that it also works in Windows PowerShell 5.1.
    foreach ($part in $Parts) { $Base = Join-Path $Base $part }
    return $Base
}

function Find-VcRedist {
    <#
    The newest Redist\MSVC\<version>\x64 folders (the C++ runtime and the OpenMP runtime) of the Visual Studio
    installations in $Root, or, when none is given, of those that vswhere and the usual folders show on this machine.
    Returns $null, or an object with Version, Crt and OpenMp.
    #>
    param([string[]]$Root = @())

    $roots = @($Root | Where-Object { $_ })
    if (-not $roots) {
        $programFilesX86 = ${env:ProgramFiles(x86)}
        if ($programFilesX86) {
            $vswhere = Join-Segments $programFilesX86 @('Microsoft Visual Studio', 'Installer', 'vswhere.exe')
            if (Test-Path -LiteralPath $vswhere) {
                $roots += @(& $vswhere -all -products '*' -property installationPath 2>$null | Where-Object { $_ })
            }
        }
        foreach ($base in @($env:ProgramFiles, $programFilesX86)) {
            if (-not $base) { continue }
            $studio = Join-Path $base 'Microsoft Visual Studio'
            foreach ($release in @(Get-ChildItem -LiteralPath $studio -Directory -ErrorAction SilentlyContinue)) {
                $roots += @(Get-ChildItem -LiteralPath $release.FullName -Directory -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName })
            }
        }
    }

    $best = $null
    foreach ($studio in $roots) {
        $redist = Join-Segments $studio @('VC', 'Redist', 'MSVC')
        foreach ($folder in @(Get-ChildItem -LiteralPath $redist -Directory -ErrorAction SilentlyContinue)) {
            # Folders are named by version (14.44.35112); others (v143) are links that carry no version.
            if ($folder.Name -notmatch '^\d+\.\d+\.\d+') { continue }
            $version = [version]($Matches[0])
            $x64 = Join-Path $folder.FullName 'x64'
            $crt = @(Get-ChildItem -LiteralPath $x64 -Directory -Filter 'Microsoft.VC*.CRT' -ErrorAction SilentlyContinue | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'msvcp140.dll') } | Select-Object -First 1)
            if (-not $crt) { continue }
            if ($best -and $best.Version -ge $version) { continue }
            $openMp = @(Get-ChildItem -LiteralPath $x64 -Directory -Filter 'Microsoft.VC*.OpenMP' -ErrorAction SilentlyContinue | Select-Object -First 1)
            $best = [pscustomobject]@{
                Version = $version
                Crt     = $crt[0].FullName
                OpenMp  = $(if ($openMp) { $openMp[0].FullName } else { $null })
            }
        }
    }
    return $best
}

function Get-VcRuntime {
    <#
    Put the Visual C++ runtime DLLs into the folder $Target, with a note of where they came from. They are taken from
    $From (a folder holding them) or, without it, from the Redist folder of the newest Visual Studio found (Microsoft
    allows these files to be redistributed with an application; they are copied unchanged).
    Returns $true, or $false with the reason in $script:VcRuntimeProblem.
    #>
    param(
        [Parameter(Mandatory)][string]$Target,
        [string]$From = '',
        [string[]]$VisualStudioRoot = @()
    )

    $script:VcRuntimeProblem = ''
    if ($From) {
        if (-not (Test-Path -LiteralPath $From -PathType Container)) {
            $script:VcRuntimeProblem = "The folder $From does not exist."
            return $false
        }
        $folders = @($From)
        $origin = $From
    } else {
        $found = Find-VcRedist -Root $VisualStudioRoot
        if (-not $found) {
            $script:VcRuntimeProblem = 'No Visual Studio with a Visual C++ Redistributable folder (VC\Redist\MSVC) was found on this machine. Install the Visual Studio Build Tools with the C++ workload, or pass -VcRuntimeDir <a folder that holds msvcp140.dll, msvcp140_1.dll and vcomp140.dll>.'
            return $false
        }
        $folders = @($found.Crt, $found.OpenMp) | Where-Object { $_ }
        $origin = "Visual Studio's Redistributable $($found.Version) ($($found.Crt))"
    }

    $byName = @{}
    foreach ($folder in $folders) {
        foreach ($pattern in $script:VcRuntimePatterns) {
            foreach ($file in @(Get-ChildItem -LiteralPath $folder -Filter $pattern -File -ErrorAction SilentlyContinue)) {
                if (-not $byName.ContainsKey($file.Name.ToLowerInvariant())) { $byName[$file.Name.ToLowerInvariant()] = $file }
            }
        }
    }
    $missing = @($script:VcRuntimeRequired | Where-Object { -not $byName.ContainsKey($_) })
    if ($missing) {
        $script:VcRuntimeProblem = "$origin lacks $($missing -join ', ')."
        return $false
    }

    $partial = "$Target.partial"
    if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $partial | Out-Null
    $notes = @("Taken from: $origin")
    foreach ($name in @($byName.Keys | Sort-Object)) {
        $file = $byName[$name]
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $partial $file.Name)
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash
        $notes += ('{0}  version {1}  sha256 {2}' -f $file.Name, $file.VersionInfo.FileVersion, $hash)
    }
    Set-Content -LiteralPath (Join-Path $partial 'versions.txt') -Value $notes -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $partial 'NOTICE.txt') -Encoding UTF8 -Value @(
        'These are the Microsoft Visual C++ runtime libraries (msvcp140*, concrt140, vcomp140), copied unchanged from the',
        'Redistributable files of Visual Studio on the machine that built this installer. KaramTC carries them so that the',
        'libraries it uses (ctranslate2, onnxruntime) load on a computer that does not have the Visual C++',
        'Redistributable. They remain Microsoft software and are redistributed under Microsoft''s terms for the Visual C++',
        'Redistributable files; versions.txt says which ones these are.'
    )
    if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
    Move-Item -LiteralPath $partial -Destination $Target
    return $true
}
