# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Python and its libraries, prepared as folders that can travel inside the installer:
#
#   * the python.org installer of the Python that the GTK runtime's wheels are for (so that winget and the internet
#     are not needed to get Python), and
#   * a "wheelhouse": every Python library KaramTC needs (PyMuPDF, Pillow, faster-whisper, PyAV and what those need),
#     built or downloaded once, at build time (so that PyPI and a C++ compiler are not needed when the application is
#     installed).
#
# Dot-source this file, then:
#
#     Get-GtkPythonMinor <gtk folder>                   # "3.14": the Python the PyGObject wheels in the runtime are for
#     Find-BuildPython <x.y>                            # a python.exe of that version on this machine, or $null
#     Get-PythonInstaller -Target <folder> -Version <x.y.z> [-Sha256 <hash>] [-InstallerPath <exe>]
#                                                       # $true when <folder> holds python-<version>-amd64.exe
#     Find-PythonInstaller <folder> <x.y>               # the path of python-<x.y>.*-amd64.exe in <folder>, or $null
#     Install-PythonFromInstaller <exe> [<log file>]    # a silent per-user installation; $true when it succeeded
#     Build-Wheelhouse -Target <folder> -Python <exe> -ProjectRoot <dir> [-ExpectMinor <x.y>] [-PipArguments ...]
#                                                       # $true when <folder> is a complete wheelhouse
#     Test-Wheelhouse <folder> [<x.y>]                  # is it complete (and for that Python)?
#
# The Get- and Build- functions never throw; they say why on the console when they return $false.
#
# Python itself is not unpacked into the installer: a virtual environment cannot be moved (it records the absolute
# path of the Python it was made from), so the installer installs Python on the user's machine and the install script
# makes the environment there. Python's installer is run per user (no administrator rights) and its result is left in
# place when KaramTC is removed, because other programs may use it.
#
# The python.org installer is a download of the exact version of the Python that builds the wheelhouse, checked
# against its Authenticode signature (it must be signed by the Python Software Foundation) and, when -Sha256 is
# given, against that hash. The hash that was seen is printed. Python releases after 3.14 are planned to come
# through the Python install manager instead of a classic installer (PEP 773): moving to one will need this
# revisited, and until then the build says it could not get the installer and the application falls back to winget.

# The Python code that prints a Python's version as "3.14". It has no double quote on purpose: Windows PowerShell 5.1
# (which the installer runs the install script with) drops the double quotes of an argument it hands to a program, so
# a snippet that had them ended in a SyntaxError, and the check "is this environment made with this Python?" said no
# every time.
$script:PythonMinorSnippet = 'import sys; print(str(sys.version_info[0]) + chr(46) + str(sys.version_info[1]))'

# Why the last Get-PythonInstaller or Build-Wheelhouse returned $false (they print it too); the build script can then
# stop with that reason (-RequirePython) instead of leaving it in the middle of a long log.
$script:BundleProblem = ''

# Runs a native command and returns its output lines; $null when it failed. Never throws.
function Invoke-QuietNative([string]$Exe, [string[]]$Arguments) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Exe @Arguments 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return $output
    } catch { return $null } finally { $ErrorActionPreference = $saved }
}

# The newest Python version ("3.14") that the PyGObject wheels in <gtk folder>\wheels are for, or $null.
function Get-GtkPythonMinor([string]$GtkFolder) {
    $best = $null
    foreach ($wheel in @(Get-ChildItem (Join-Path $GtkFolder 'wheels') -Filter 'pygobject*.whl' -ErrorAction SilentlyContinue)) {
        if ($wheel.Name -match '-cp(\d)(\d+)-cp\d+-win_amd64\.whl$') {
            $version = [version]("{0}.{1}" -f $Matches[1], $Matches[2])
            if (-not $best -or $version -gt $best) { $best = $version }
        }
    }
    if ($best) { return "$($best.Major).$($best.Minor)" }
    return $null
}

# A python.exe of version <x.y> (64-bit) on this machine: the one on PATH, else the one the py launcher knows.
function Find-BuildPython([string]$Minor) {
    $candidates = @()
    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath -and $onPath.Source -notlike '*\WindowsApps\*') { $candidates += $onPath.Source }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $viaLauncher = Invoke-QuietNative 'py' @("-$Minor-64", '-c', 'import sys; print(sys.executable)')
        if ($viaLauncher) { $candidates += ([string]($viaLauncher | Select-Object -First 1)).Trim() }
    }
    foreach ($candidate in $candidates) {
        $reported = Invoke-QuietNative $candidate @('-c', $script:PythonMinorSnippet)
        if ($reported -and ([string]($reported | Select-Object -First 1)).Trim() -eq $Minor) { return $candidate }
    }
    return $null
}

function Find-PythonInstaller([string]$Folder, [string]$Minor) {
    if (-not $Folder -or -not (Test-Path -LiteralPath $Folder)) { return $null }
    $found = Get-ChildItem -LiteralPath $Folder -Filter "python-$Minor.*-amd64.exe" -ErrorAction SilentlyContinue |
             Sort-Object Name -Descending | Select-Object -First 1
    if ($found) { return $found.FullName }
    return $null
}

# Throws unless the file is validly signed (Authenticode) by the Python Software Foundation. Only Windows can check a
# signature, and the installer is only run there, so elsewhere there is nothing to check.
function Assert-PythonInstallerSignature([string]$File) {
    if ($env:OS -ne 'Windows_NT') { return }
    $signature = Get-AuthenticodeSignature -LiteralPath $File
    if ($signature.Status -ne 'Valid') { throw "The installer's signature is not valid ($($signature.Status))." }
    if ([string]$signature.SignerCertificate.Subject -notmatch 'Python Software Foundation') {
        throw "The installer is not signed by the Python Software Foundation (signed by $($signature.SignerCertificate.Subject))."
    }
    Write-Host 'OK  The installer is signed by the Python Software Foundation.' -ForegroundColor Green
}

function Get-PythonInstaller {
    param(
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][string]$Version,          # 3.14.9, or 3.15.0rc2 for a pre-release
        [string]$Sha256 = '',
        # A python-*-amd64.exe that is already on this machine: nothing is downloaded (offline builds).
        [string]$InstallerPath = ''
    )

    $name = "python-$Version-amd64.exe"
    $work = Join-Path ([IO.Path]::GetTempPath()) ('python-installer-' + [guid]::NewGuid().ToString('N'))
    $script:BundleProblem = ''
    try {
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
        New-Item -ItemType Directory -Force -Path $work | Out-Null

        if ($InstallerPath) {
            if (-not (Test-Path -LiteralPath $InstallerPath)) { throw "$InstallerPath does not exist." }
            $file = (Resolve-Path -LiteralPath $InstallerPath).Path
        } else {
            $directory = $Version -replace '^(\d+\.\d+\.\d+).*$', '$1'
            $file = Join-Path $work $name
            Write-Host "==> Downloading Python $Version (python.org)..." -ForegroundColor Cyan
            Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$directory/$name" -OutFile $file -UseBasicParsing
        }

        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash
        if ($Sha256 -and ($hash -ne $Sha256.ToUpper())) { throw "The file does not match the expected SHA256 (got $hash, expected $($Sha256.ToUpper()))." }
        if ($Sha256) { Write-Host "OK  Python installer SHA256 $hash matches." -ForegroundColor Green }
        else { Write-Host "!!  No SHA256 to check the Python installer against. Its SHA256 is $hash." -ForegroundColor Yellow }

        Assert-PythonInstallerSignature $file

        New-Item -ItemType Directory -Force -Path $Target | Out-Null
        Get-ChildItem -LiteralPath $Target -Filter 'python-*-amd64.exe' -ErrorAction SilentlyContinue | Remove-Item -Force   # An older one is never left beside it.
        Copy-Item -LiteralPath $file -Destination (Join-Path $Target $name) -Force
        return $true
    } catch {
        $script:BundleProblem = "The Python installer could not be prepared: $($_.Exception.Message)"
        Write-Host "!!  $script:BundleProblem" -ForegroundColor Yellow
        return $false
    } finally {
        if (Test-Path $work) { Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue }
    }
}

# Runs a python.org installer silently for the current user: no administrator rights, nothing added to PATH, no
# launcher, tests, documentation, shortcuts or file associations. It lands in %LOCALAPPDATA%\Programs\Python\Python3xx,
# where the install script looks first. Gives up (and ends the installer) after 15 minutes.
function Install-PythonFromInstaller([string]$Installer, [string]$LogFile = '') {
    $arguments = @('/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0', 'Include_test=0', 'Include_doc=0', 'Shortcuts=0', 'AssociateFiles=0')
    if ($LogFile) { $arguments += @('/log', "`"$LogFile`"") }
    try {
        $process = Start-Process -FilePath $Installer -ArgumentList $arguments -PassThru
        if (-not $process.WaitForExit(15 * 60 * 1000)) {
            if ($env:OS -eq 'Windows_NT') { & taskkill /PID $process.Id /T /F 2>&1 | Out-Null } else { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
            $global:LASTEXITCODE = 0
            Write-Host '!!  The Python installer did not finish in 15 minutes and was stopped.' -ForegroundColor Yellow
            return $false
        }
        # 3010: installed, a restart is advisable (not needed to use it).
        return (@(0, 3010) -contains $process.ExitCode)
    } catch {
        Write-Host "!!  The Python installer could not be run: $($_.Exception.Message)" -ForegroundColor Yellow
        return $false
    }
}

# The file that says which Python a wheelhouse was verified for (written by Build-Wheelhouse once pip has shown that
# the project's libraries can be installed from the folder alone for that Python).
$script:WheelhouseMarker = 'for-python.txt'

# Why a folder cannot be used as the wheelhouse for Python <x.y> ('' when it can). A wheelhouse has the libraries whose
# absence would send the installation back to the internet (the big compiled ones: PyMuPDF, Pillow, PyAV and
# CTranslate2, the engine under faster-whisper), and, when a Python version is given, was verified for that version.
function Get-WheelhouseProblem([string]$Folder, [string]$Minor = '') {
    if (-not $Folder -or -not (Test-Path -LiteralPath $Folder)) { return "there is no folder $Folder" }
    $names = @(Get-ChildItem -LiteralPath $Folder -Filter '*.whl' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name.ToLower() })
    foreach ($needed in 'pymupdf-', 'pillow-', 'faster_whisper-', 'ctranslate2-', 'av-') {
        if (-not @($names | Where-Object { $_.StartsWith($needed) })) { return "it has no $($needed.TrimEnd('-')) wheel (it has $($names.Count) wheels)" }
    }
    if ($Minor) {
        $marker = Join-Path $Folder $script:WheelhouseMarker
        $verified = if (Test-Path -LiteralPath $marker) { (Get-Content -LiteralPath $marker -TotalCount 1).Trim() } else { '' }
        if ($verified -ne $Minor) {
            $what = if ($verified) { "Python $verified" } else { 'no Python version' }
            return "it was verified for $what, not for Python $Minor"
        }
    }
    return ''
}

function Test-Wheelhouse([string]$Folder, [string]$Minor = '') {
    return -not (Get-WheelhouseProblem $Folder $Minor)
}

# Runs `python -m pip <arguments>` with its output on the console only (what a function prints is part of what it
# returns) and gives back the exit code and the last lines of what pip said, for the reason of a failure. Its error
# lines are made plain text first: Windows PowerShell 5.1 turns a native command's stderr into errors under 'Stop'.
function Invoke-Pip([string]$Python, [string[]]$Arguments) {
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $pipLines = @()          # (Tee-Object leaves the variable unset when pip prints nothing, which strict mode does not allow.)
    try { & $Python -m pip @Arguments 2>&1 | ForEach-Object { "$_" } | Tee-Object -Variable pipLines | Out-Host }
    finally { $ErrorActionPreference = $savedPreference }
    $code = $LASTEXITCODE
    $tail = (@($pipLines | Where-Object { $_ -and $_.Trim() } | Select-Object -Last 4) | ForEach-Object { $_.Trim() }) -join ' | '
    return [pscustomobject]@{ ExitCode = $code; Tail = $tail }
}

# Builds the wheelhouse with pip: wheels for everything requirements.txt asks for (and what that needs in turn), for
# the Python that is $Python. A package that only comes as source is built into a wheel here, which is fine for a pure
# Python one; one that needs a C++ compiler makes the build stop and say so.
function Build-Wheelhouse {
    param(
        [Parameter(Mandatory)][string]$Target,
        [Parameter(Mandatory)][string]$Python,
        [Parameter(Mandatory)][string]$ProjectRoot,
        # The Python version the wheels have to be for (the one the GTK runtime's wheels are for).
        [string]$ExpectMinor = '',
        # More arguments for pip (a test gives a local index).
        [string[]]$PipArguments = @()
    )

    $work = Join-Path ([IO.Path]::GetTempPath()) ('wheelhouse-' + [guid]::NewGuid().ToString('N'))
    $staging = $Target + '.partial'
    $script:BundleProblem = ''
    try {
        New-Item -ItemType Directory -Force -Path $work | Out-Null
        $reported = Invoke-QuietNative $Python @('-c', $script:PythonMinorSnippet)
        if (-not $reported) { throw "$Python could not be run." }
        $minor = ([string]($reported | Select-Object -First 1)).Trim()
        if ($ExpectMinor -and $minor -ne $ExpectMinor) {
            throw "$Python is Python $minor, but the wheels have to be for Python $ExpectMinor (the one the GTK runtime's wheels are for)."
        }

        # What the project asks for, from its own requirements.txt.
        $requirements = Join-Path $ProjectRoot 'requirements.txt'
        if (-not (Test-Path -LiteralPath $requirements)) { throw "There is no requirements.txt in $ProjectRoot." }

        if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $staging | Out-Null
        Write-Host "==> Building the wheelhouse for Python $minor (the Python libraries that go inside the installer)..." -ForegroundColor Cyan
        $wheel = Invoke-Pip $Python (@('wheel', '--wheel-dir', $staging, '--prefer-binary', '-r', $requirements) + $PipArguments)
        if ($wheel.ExitCode -ne 0) { throw "pip wheel failed (exit code $($wheel.ExitCode)): $($wheel.Tail)" }

        # Pip has the last word on whether these wheels are enough: everything the project asks for, for this Python,
        # from this folder alone, with nothing to build and nothing to download.
        Write-Host '==> Checking that pip can install everything from the wheelhouse alone...' -ForegroundColor Cyan
        $verify = Invoke-Pip $Python @('install', '--dry-run', '--no-index', '--find-links', $staging, '--only-binary=:all:', '--quiet', '-r', $requirements)
        if ($verify.ExitCode -ne 0) { throw "pip cannot install the libraries from the wheelhouse alone (exit code $($verify.ExitCode)): $($verify.Tail)" }
        $problem = Get-WheelhouseProblem $staging
        if ($problem) { throw "pip finished, but the wheelhouse is not usable: $problem." }
        Set-Content -LiteralPath (Join-Path $staging $script:WheelhouseMarker) -Value $minor -Encoding ASCII

        if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
        Move-Item -LiteralPath $staging -Destination $Target
        $count = @(Get-ChildItem -LiteralPath $Target -Filter '*.whl').Count
        Write-Host "OK  $count wheels for Python $minor." -ForegroundColor Green
        return $true
    } catch {
        $script:BundleProblem = "The wheelhouse could not be built: $($_.Exception.Message)"
        Write-Host "!!  $script:BundleProblem" -ForegroundColor Yellow
        return $false
    } finally {
        if (Test-Path $work) { Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue }
        if (Test-Path $staging) { Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
