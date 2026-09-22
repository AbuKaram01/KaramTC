# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Python's installer and the Python libraries (a "wheelhouse") inside the Windows installer: scripts/python-bundle.ps1,
and the build, install, installer and CI scripts that carry and use them.

The PowerShell is run with PowerShell 7 (pwsh) where it is installed. The wheelhouse tests run the real pip of the Python
that runs the tests against a folder of stand-in wheels (empty ones, which pip accepts), so what pip says about them is
real; what the real libraries look like for Python 3.14 on Windows is what the CI job that builds the installer (and the
manual installer job) check.
"""

import hashlib
import os
import re
import shutil
import subprocess
import stat
import sys
import sysconfig
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ROOT / "packaging" / "windows"
BUNDLE = ROOT / "scripts" / "python-bundle.ps1"
needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 (pwsh) is not available")


def run_bundle_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "bundle-case.ps1"
    # Strict mode like the scripts that use python-bundle.ps1 (an unset variable is an error there, not an empty value).
    script.write_text(f"Set-StrictMode -Version 2.0\n$ErrorActionPreference = 'Stop'\n. '{BUNDLE}'\n{body}\n", encoding="utf-8")
    return subprocess.run(["pwsh", "-NoProfile", "-File", str(script)], capture_output=True, text=True, check=False)


# The files these tests make are not signed, and on Windows the signature is checked for real (its own test below).
NO_SIGNATURE_CHECK = "function Assert-PythonInstallerSignature([string]$File) { }\n"

# What a wheelhouse has to hold, and what requirements.txt calls those libraries.
NEEDED = ("pymupdf", "pillow", "faster_whisper", "ctranslate2", "av")


def make_wheel(folder: Path, name: str, version: str = "1.0", tag: str = "py3-none-any", requires: tuple[str, ...] = ()) -> Path:
    """A real (empty) wheel that pip accepts: just its metadata."""
    folder.mkdir(parents=True, exist_ok=True)
    dist = f"{name.replace('-', '_')}-{version}"
    path = folder / f"{dist}-{tag}.whl"
    needs = "".join(f"Requires-Dist: {requirement}\n" for requirement in requires)
    with zipfile.ZipFile(path, "w") as wheel:
        wheel.writestr(f"{dist}.dist-info/METADATA", f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n{needs}")
        wheel.writestr(f"{dist}.dist-info/WHEEL", f"Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: {tag}\n")
        wheel.writestr(f"{dist}.dist-info/RECORD", "")
    return path


def this_pythons_tag() -> tuple[str, str, str]:
    """("3.12", "cp312-cp312-linux_x86_64", "linux_x86_64"): a wheel tag that pip accepts for the Python running the tests."""
    major, minor = sys.version_info[:2]
    platform = sysconfig.get_platform().replace("-", "_").replace(".", "_")
    return f"{major}.{minor}", f"cp{major}{minor}-cp{major}{minor}-{platform}", platform


def make_wheelhouse_folder(folder: Path, minor: str = "3.14", skip: tuple[str, ...] = (), marker: str | None = None) -> Path:
    """A folder that looks like a built wheelhouse; the marker says for which Python (the default: *minor*)."""
    folder.mkdir(parents=True, exist_ok=True)
    tag = f"cp{minor.replace('.', '')}"
    for name, wheel_tag in (("PyMuPDF", "cp310-abi3-win_amd64"), ("pillow", f"{tag}-{tag}-win_amd64"), ("faster_whisper", "py3-none-any"),
                            ("ctranslate2", f"{tag}-{tag}-win_amd64"), ("av", f"{tag}-{tag}-win_amd64"), ("tqdm", "py3-none-any")):
        if name.lower() not in skip:
            (folder / f"{name}-1.0-{wheel_tag}.whl").write_bytes(b"x")
    (folder / "for-python.txt").write_text((marker or minor) + "\n", encoding="ascii")
    return folder


def make_project(folder: Path) -> Path:
    """A project whose requirements.txt looks like KaramTC's (comments included), for stand-in libraries."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "requirements.txt").write_text(
        "# Version bounds, not exact pins.\n"
        "pymupdf>=1.0,<2.0\n"
        "Pillow>=1.0,<13.0\n"
        "\n"
        "# Speech recognition.\n"
        "faster-whisper>=1.0,<2.0\n"
        "av>=1.0,<19.0\n",
        encoding="utf-8",
    )
    return folder


def make_index(folder: Path, python_tag: str, compiled_tag: str | None = None) -> Path:
    """Stand-in wheels for everything make_project asks for, and for what faster-whisper needs in turn (CTranslate2)."""
    for name in ("pymupdf", "Pillow", "av", "ctranslate2"):
        make_wheel(folder, name, tag=compiled_tag or python_tag)
    make_wheel(folder, "faster-whisper", requires=("ctranslate2>=1.0",))
    return folder


# -- asking a Python which version it is ---------------------------------------------------------------------------

def test_no_python_snippet_handed_to_a_program_has_a_double_quote():
    """Windows PowerShell 5.1 (it runs the install script) drops the double quotes of an argument that it hands to a
    program: `python -c 'print("%d.%d" % ...)'` was a SyntaxError there, so the environment of the same Python was
    thought to be another one and was recreated on every run, and a Python on PATH was never found."""
    scripts = sorted((ROOT / "scripts").glob("*.ps1")) + sorted((ROOT / "packaging").rglob("*.ps1"))
    assert scripts
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        for snippet in re.findall(r"'-c',\s*'([^']*)'", text):
            assert '"' not in snippet, f"{script.name}: {snippet}"
    assert '"' not in re.search(r"PythonMinorSnippet = '([^']*)'", BUNDLE.read_text(encoding="utf-8")).group(1)


def test_the_version_checks_use_the_one_snippet_and_it_prints_what_they_compare_with():
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    assert install.count("@('-c', $script:PythonMinorSnippet)") == 2                    # The Python on PATH, and the existing environment.
    assert BUNDLE.read_text(encoding="utf-8").count("@('-c', $script:PythonMinorSnippet)") == 2     # The Python that builds the wheelhouse.
    snippet = re.search(r"PythonMinorSnippet = '([^']*)'", BUNDLE.read_text(encoding="utf-8")).group(1)
    run = subprocess.run([sys.executable, "-c", snippet], capture_output=True, text=True, check=True)
    assert run.stdout.strip() == f"{sys.version_info[0]}.{sys.version_info[1]}"          # "3.14", the form the install script compares.


# -- finding and copying Python's installer ------------------------------------------------------------------------

@needs_pwsh
def test_the_python_installer_of_the_right_version_is_found(tmp_path):
    for name in ("python-3.14.9-amd64.exe", "python-3.15.0-amd64.exe", "python-3.1.5-amd64.exe", "python-3.14.9-arm64.exe", "notes.txt"):
        (tmp_path / "python" / name).parent.mkdir(exist_ok=True)
        (tmp_path / "python" / name).write_bytes(b"x")
    found = run_bundle_script(tmp_path, f"Write-Output (\"FOUND=\" + (Find-PythonInstaller '{tmp_path / 'python'}' '3.14'))")
    assert f"FOUND={tmp_path / 'python' / 'python-3.14.9-amd64.exe'}" in found.stdout, found.stdout + found.stderr
    none = run_bundle_script(tmp_path, f"Write-Output (\"FOUND=[\" + (Find-PythonInstaller '{tmp_path / 'python'}' '3.13') + \"]\")")
    assert "FOUND=[]" in none.stdout, none.stdout + none.stderr
    nothing = run_bundle_script(tmp_path, f"Write-Output (\"FOUND=[\" + (Find-PythonInstaller '{tmp_path / 'nowhere'}' '3.14') + \"]\")")
    assert "FOUND=[]" in nothing.stdout, nothing.stdout + nothing.stderr


@needs_pwsh
def test_a_python_installer_is_copied_under_its_own_name_and_replaces_an_older_one(tmp_path):
    installer = tmp_path / "somewhere" / "installer.exe"
    installer.parent.mkdir()
    installer.write_bytes(b"MZ python installer")
    target = tmp_path / "out" / "python"
    target.mkdir(parents=True)
    (target / "python-3.14.1-amd64.exe").write_bytes(b"old")
    result = run_bundle_script(tmp_path, NO_SIGNATURE_CHECK + f"$ok = Get-PythonInstaller -Target '{target}' -Version 3.14.9 -InstallerPath '{installer}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr
    assert sorted(path.name for path in target.iterdir()) == ["python-3.14.9-amd64.exe"]
    assert (target / "python-3.14.9-amd64.exe").read_bytes() == b"MZ python installer"
    assert hashlib.sha256(b"MZ python installer").hexdigest().upper() in result.stdout       # The hash that was seen is printed.


@needs_pwsh
def test_a_python_installer_must_match_the_hash_it_is_pinned_to(tmp_path):
    installer = tmp_path / "installer.exe"
    installer.write_bytes(b"MZ python installer")
    right = hashlib.sha256(installer.read_bytes()).hexdigest()
    wrong = ("0" if right[0] != "0" else "1") + right[1:]
    bad = run_bundle_script(tmp_path, NO_SIGNATURE_CHECK + f"$ok = Get-PythonInstaller -Target '{tmp_path / 'bad'}' -Version 3.14.9 -InstallerPath '{installer}' -Sha256 '{wrong}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=False" in bad.stdout and "does not match the expected SHA256" in bad.stdout, bad.stdout + bad.stderr
    assert not (tmp_path / "bad").exists()
    good = run_bundle_script(tmp_path, NO_SIGNATURE_CHECK + f"$ok = Get-PythonInstaller -Target '{tmp_path / 'good'}' -Version 3.14.9 -InstallerPath '{installer}' -Sha256 '{right.upper()}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=True" in good.stdout, good.stdout + good.stderr
    missing = run_bundle_script(tmp_path, NO_SIGNATURE_CHECK + f"$ok = Get-PythonInstaller -Target '{tmp_path / 'm'}' -Version 3.14.9 -InstallerPath '{tmp_path / 'none.exe'}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=False" in missing.stdout and "does not exist" in missing.stdout
    reason = run_bundle_script(tmp_path, NO_SIGNATURE_CHECK + f"$null = Get-PythonInstaller -Target '{tmp_path / 'r'}' -Version 3.14.9 -InstallerPath '{tmp_path / 'none.exe'}'\nWrite-Output \"WHY=$script:BundleProblem\"")
    assert "WHY=The Python installer could not be prepared: " in reason.stdout and "does not exist" in reason.stdout    # The build can say why.


@needs_pwsh
@pytest.mark.skipif(sys.platform != "win32", reason="only Windows can check an Authenticode signature")
def test_a_python_installer_must_be_validly_signed_by_the_python_software_foundation(tmp_path):
    unsigned = tmp_path / "python-3.14.9-amd64.exe"
    unsigned.write_bytes(b"MZ not really an installer")
    refused = run_bundle_script(tmp_path, f"$ok = Get-PythonInstaller -Target '{tmp_path / 'out'}' -Version 3.14.9 -InstallerPath '{unsigned}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=False" in refused.stdout and "signature is not valid" in refused.stdout, refused.stdout + refused.stderr
    assert not (tmp_path / "out").exists()                                             # Nothing is copied from a file that is not trusted.
    # PowerShell's own program is validly signed, by Microsoft: a good signature from the wrong signer is refused too.
    other = run_bundle_script(tmp_path, "try { Assert-PythonInstallerSignature (Get-Process -Id $PID).Path; Write-Output 'RESULT=accepted' } catch { Write-Output \"RESULT=$($_.Exception.Message)\" }")
    assert "RESULT=accepted" not in other.stdout and "RESULT=" in other.stdout, other.stdout + other.stderr
    assert "not signed by the Python Software Foundation" in other.stdout or "signature is not valid" in other.stdout, other.stdout


def test_the_signature_of_the_python_installer_is_checked_before_it_is_copied():
    text = BUNDLE.read_text(encoding="utf-8")
    assert "Get-AuthenticodeSignature" in text and "Python Software Foundation" in text
    body = text.split("function Get-PythonInstaller")[1]
    assert body.index("Assert-PythonInstallerSignature $file") < body.index("Copy-Item -LiteralPath $file")


@needs_pwsh
@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in installer is a POSIX script")
@pytest.mark.parametrize("exit_code, expected", [(0, True), (1, False), (5, False)])      # (3010, "restart advisable", is 194 on a POSIX system.)
def test_python_is_installed_silently_for_the_current_user(tmp_path, exit_code, expected):
    record = tmp_path / "arguments.txt"
    installer = tmp_path / "python-3.14.9-amd64.exe"
    installer.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{record}"\nexit {exit_code}\n', encoding="utf-8")
    installer.chmod(installer.stat().st_mode | stat.S_IXUSR)
    result = run_bundle_script(tmp_path, f"$ok = Install-PythonFromInstaller '{installer}' '{tmp_path / 'python.log'}'\nWrite-Output \"RESULT=$ok\"")
    assert f"RESULT={expected}" in result.stdout, result.stdout + result.stderr
    arguments = record.read_text(encoding="utf-8").split()
    for needed in ("/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_launcher=0", "Include_test=0", "Shortcuts=0", "AssociateFiles=0", "/log"):
        assert needed in arguments, arguments
    assert "InstallAllUsers=1" not in arguments                 # Never needs administrator rights.
    assert "@(0, 3010) -contains $process.ExitCode" in BUNDLE.read_text(encoding="utf-8")     # "Installed, a restart is advisable" is a success.


# -- what a wheelhouse is, and building one --------------------------------------------------------------------------

@needs_pwsh
def test_a_wheelhouse_is_complete_only_with_what_the_installation_needs(tmp_path):
    def check(folder, minor=""):
        result = run_bundle_script(tmp_path, f"Write-Output \"RESULT=$(Test-Wheelhouse '{folder}' '{minor}')\"")
        return "RESULT=True" in result.stdout

    assert check(make_wheelhouse_folder(tmp_path / "complete"))
    assert check(tmp_path / "complete", "3.14")
    assert not check(tmp_path / "complete", "3.13")                                  # It was verified for 3.14.
    # What pip accepts for a Python is not guessed from the wheels' names: the wheel's tag does not matter, the marker does.
    assert check(make_wheelhouse_folder(tmp_path / "abi3", marker="3.14"), "3.14")
    assert not check(make_wheelhouse_folder(tmp_path / "unverified", marker="3.13"), "3.14")
    (tmp_path / "unmarked").mkdir()
    for wheel in (tmp_path / "complete").glob("*.whl"):
        (tmp_path / "unmarked" / wheel.name).write_bytes(b"x")
    assert check(tmp_path / "unmarked") and not check(tmp_path / "unmarked", "3.14")     # No marker: not verified for any Python.
    for missing in NEEDED:
        assert not check(make_wheelhouse_folder(tmp_path / f"no-{missing}", skip=(missing,))), missing


@needs_pwsh
def test_a_wheelhouse_that_cannot_be_used_says_why(tmp_path):
    def why(folder, minor=""):
        return run_bundle_script(tmp_path, f"Write-Output \"WHY=[$(Get-WheelhouseProblem '{folder}' '{minor}')]\"").stdout

    assert "WHY=[]" in why(make_wheelhouse_folder(tmp_path / "ok"), "3.14")
    assert "no pymupdf wheel" in why(make_wheelhouse_folder(tmp_path / "a", skip=("pymupdf",)))
    assert "no ctranslate2 wheel" in why(make_wheelhouse_folder(tmp_path / "c", skip=("ctranslate2",)))
    assert "verified for Python 3.13, not for Python 3.14" in why(make_wheelhouse_folder(tmp_path / "b", marker="3.13"), "3.14")
    assert "there is no folder" in why(tmp_path / "nowhere")


def test_the_wheelhouse_check_names_the_libraries_that_requirements_txt_asks_for():
    """If a library is added to requirements.txt (or renamed), a wheelhouse without it must not pass as complete."""
    asked = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            asked.add(re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].lower().replace("-", "_"))
    named = set(re.search(r"foreach \(\$needed in ([^)]*?)\) \{", BUNDLE.read_text(encoding="utf-8")).group(1).replace("'", "").replace("-", "").split(", "))
    named = {name.replace("-", "") for name in named}
    assert asked == {"pymupdf", "pillow", "faster_whisper", "av"}, asked
    assert asked <= named, (asked, named)                                              # Every top-level library is checked for ...
    assert named - asked == {"ctranslate2"}, named - asked                             # ... and so is the engine under faster-whisper.


def test_the_wheelhouse_is_checked_with_nothing_but_itself():
    """pip must be shown the wheelhouse alone: with an index in reach it would fill in what is missing, and the check
    would pass for a wheelhouse that only works with the internet."""
    text = BUNDLE.read_text(encoding="utf-8")
    verify = text.split("Checking that pip can install everything from the wheelhouse alone")[1].split("if ($verify.ExitCode")[0]
    for needed in ("'--dry-run'", "'--no-index'", "'--find-links', $staging", "'--only-binary=:all:'", "'-r', $requirements"):
        assert needed in verify, needed


@needs_pwsh
def test_the_python_of_the_gtk_runtime_is_the_newest_its_wheels_are_for(tmp_path):
    wheels = tmp_path / "gtk" / "wheels"
    wheels.mkdir(parents=True)
    for name in ("PyGObject-3.54.0-cp313-cp313-win_amd64.whl", "PyGObject-3.54.0-cp314-cp314-win_amd64.whl", "pycairo-1.28.0-cp315-cp315-win_amd64.whl"):
        (wheels / name).write_bytes(b"x")
    found = run_bundle_script(tmp_path, f"Write-Output \"MINOR=$(Get-GtkPythonMinor '{tmp_path / 'gtk'}')\"")
    assert "MINOR=3.14" in found.stdout, found.stdout + found.stderr                  # pycairo does not count.
    nothing = run_bundle_script(tmp_path, f"Write-Output \"MINOR=[$(Get-GtkPythonMinor '{tmp_path / 'nowhere'}')]\"")
    assert "MINOR=[]" in nothing.stdout


@needs_pwsh
def test_the_wheelhouse_is_built_from_what_requirements_txt_asks_for_and_what_that_needs(tmp_path):
    minor, tag, _ = this_pythons_tag()
    index = make_index(tmp_path / "index", tag)
    target = tmp_path / "out" / "wheelhouse"
    result = run_bundle_script(
        tmp_path,
        f"$ok = Build-Wheelhouse -Target '{target}' -Python '{sys.executable}' -ProjectRoot '{make_project(tmp_path / 'project')}' -ExpectMinor '{minor}' "
        f"-PipArguments '--no-index','--find-links','{index}'\nWrite-Output \"RESULT=$ok\"",
    )
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr
    names = sorted(path.name for path in target.iterdir())
    for library in ("pymupdf-", "pillow-", "av-", "faster_whisper-", "ctranslate2-"):          # ctranslate2 only because faster-whisper needs it.
        assert any(name.lower().startswith(library) for name in names), (library, names)
    assert not (tmp_path / "out" / "wheelhouse.partial").exists()
    assert (target / "for-python.txt").read_text(encoding="ascii").strip() == minor        # Verified by pip for this Python.
    assert "Checking that pip can install everything from the wheelhouse alone" in result.stdout


@needs_pwsh
def test_the_wheelhouse_does_not_depend_on_how_a_compiled_wheel_is_tagged(tmp_path):
    """Whether a wheel suits this Python is for pip to say, not for the wheel's file name (PyMuPDF's wheels are abi3)."""
    minor, _, platform = this_pythons_tag()
    index = make_index(tmp_path / "index", "py3-none-any", compiled_tag=f"cp38-abi3-{platform}")
    target = tmp_path / "out" / "wheelhouse"
    result = run_bundle_script(
        tmp_path,
        f"$ok = Build-Wheelhouse -Target '{target}' -Python '{sys.executable}' -ProjectRoot '{make_project(tmp_path / 'project')}' -ExpectMinor '{minor}' "
        f"-PipArguments '--no-index','--find-links','{index}'\nWrite-Output \"RESULT=$ok\"",
    )
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr


@needs_pwsh
def test_a_wheelhouse_for_another_python_or_with_a_missing_library_is_refused_and_leaves_nothing(tmp_path):
    minor, tag, _ = this_pythons_tag()
    project = make_project(tmp_path / "project")
    index = make_index(tmp_path / "index", tag)

    wrong = run_bundle_script(
        tmp_path,
        f"$ok = Build-Wheelhouse -Target '{tmp_path / 'wrong'}' -Python '{sys.executable}' -ProjectRoot '{project}' -ExpectMinor '3.0' "
        f"-PipArguments '--no-index','--find-links','{index}'\nWrite-Output \"RESULT=$ok\"",
    )
    assert "RESULT=False" in wrong.stdout and "have to be for Python 3.0" in wrong.stdout, wrong.stdout + wrong.stderr

    (index / next(path.name for path in index.iterdir() if path.name.startswith("faster_whisper"))).unlink()      # pip cannot find it any more.
    missing = run_bundle_script(
        tmp_path,
        f"$ok = Build-Wheelhouse -Target '{tmp_path / 'missing'}' -Python '{sys.executable}' -ProjectRoot '{project}' -ExpectMinor '{minor}' "
        f"-PipArguments '--no-index','--find-links','{index}'\nWrite-Output \"RESULT=$ok\"",
    )
    assert "RESULT=False" in missing.stdout and "pip wheel failed" in missing.stdout, missing.stdout + missing.stderr
    assert "faster-whisper" in missing.stdout.split("pip wheel failed")[1]            # The reason carries what pip complained about.
    assert not (tmp_path / "wrong").exists() and not (tmp_path / "missing").exists() and not (tmp_path / "missing.partial").exists()

    # A PyMuPDF wheel built for some other Python is no use: pip does not accept it, so there is no wheelhouse.
    other = make_index(tmp_path / "other-index", tag)
    for wheel in other.glob("pymupdf-*"):
        wheel.unlink()
    make_wheel(other, "pymupdf", tag="cp27-cp27m-win_amd64")
    foreign = run_bundle_script(
        tmp_path,
        f"$ok = Build-Wheelhouse -Target '{tmp_path / 'foreign'}' -Python '{sys.executable}' -ProjectRoot '{project}' -ExpectMinor '{minor}' "
        f"-PipArguments '--no-index','--find-links','{other}'\nWrite-Output \"RESULT=$ok\"",
    )
    assert "RESULT=False" in foreign.stdout and "pymupdf" in foreign.stdout.lower() and not (tmp_path / "foreign").exists(), foreign.stdout

    # A project without requirements.txt has nothing to build a wheelhouse from.
    empty = tmp_path / "empty-project"
    empty.mkdir()
    nothing = run_bundle_script(
        tmp_path,
        f"$ok = Build-Wheelhouse -Target '{tmp_path / 'nothing'}' -Python '{sys.executable}' -ProjectRoot '{empty}' -ExpectMinor '{minor}'\nWrite-Output \"RESULT=$ok\"",
    )
    assert "RESULT=False" in nothing.stdout and "no requirements.txt" in nothing.stdout, nothing.stdout + nothing.stderr
    assert not (tmp_path / "nothing").exists()


# -- the scripts that build, carry and use them ----------------------------------------------------------------------

def test_the_install_script_prefers_what_the_installer_carries_and_falls_back_to_the_internet():
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    assert ". (Join-Path $PSScriptRoot 'python-bundle.ps1')" in install
    # Python: the installer that came along, then winget.
    python_step = install.split("function Install-Python")[1].split("$wheelDir =")[0]
    assert python_step.index("Find-PythonInstaller") < python_step.index("Install-PythonFromInstaller") < python_step.index("winget install")
    assert "installer that came with KaramTC" in python_step
    assert "if (Install-PythonFromInstaller $bundled $pythonLog) { return }" in python_step          # Only a finished installation ends the search.
    # The libraries: from the wheelhouse when it is for this Python, with no index; if that fails, downloaded as before.
    assert "$offline = Test-Wheelhouse $wheelhouse $chosen" in install
    assert "if (-not $offline) { Pip @('install', '--upgrade', 'pip', '--quiet') }" in install
    assert "'--no-index', '--find-links', $wheelhouse, '--only-binary', ':all:', '-r', $requirements" in install
    assert "installed from the wheelhouse (no internet needed)" in install
    assert "downloading them instead" in install and "if (-not $installed) { Pip @('install', '--quiet', '-r', $requirements) }" in install
    # Offline is only tried for the full installation; -SkipHeavy (the tests) installs what it names, from the internet.
    heavy = install.split("Info 'Installing the Python dependencies...'")[1].split("Ok 'Python dependencies installed.'")[0]
    assert heavy.index("if ($SkipHeavy)") < heavy.index("$offline") and "pytest" in heavy.split("} else {")[0]


def test_trying_pip_does_not_turn_what_pip_prints_into_its_answer():
    """Try-Pip is used as `if (Try-Pip ...)`: whatever a function prints becomes part of what it returns, which would make every answer true."""
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    body = install.split("function Try-Pip")[1].split("}\n")[0]
    assert "-m pip @Arguments | Out-Host" in body and "return ($LASTEXITCODE -eq 0)" in body
    assert "$installed = Try-Pip" in install


def test_the_build_prepares_python_and_its_libraries_for_the_python_of_the_gtk_runtime():
    build = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    assert ". (Join-Path $ProjectRoot 'scripts\\python-bundle.ps1')" in build
    assert "[switch]$NoPython" in build and "[string]$PythonExe" in build and "[string]$PythonInstaller" in build and "[string]$PythonInstallerSha256" in build
    assert "[switch]$RequirePython" in build and 'throw "-RequirePython: $Message"' in build and build.count("Skip-PythonPart ") >= 4
    assert build.count("$script:BundleProblem") == 2                                    # Both the installer's and the libraries' reasons.
    assert build.index("Get-PortableGtk -Target") < build.index("Get-GtkPythonMinor") < build.index("Get-PythonInstaller -Target") < build.index("ISCC")
    assert "-ExpectMinor $minor" in build                                              # The wheels are for the runtime's Python.
    assert "platform.python_version()" in build                                        # The installer is the build Python's own version.
    assert build.index("Remove-Item (Join-Path $PSScriptRoot $stale)") < build.index("Get-PythonInstaller -Target")     # Never an old one.
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/packaging/python/" in ignore and "/packaging/wheelhouse/" in ignore


def test_the_inno_script_carries_python_and_the_wheelhouse_only_when_the_build_prepared_them():
    iss = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    assert 'Source: "..\\..\\scripts\\python-bundle.ps1"; DestDir: "{app}\\scripts"' in iss
    for folder, define in (("python", "PythonFolder"), ("wheelhouse", "WheelFolder")):
        assert f'#define {define} SourcePath + "\\..\\{folder}"' in iss
        assert f'#if DirExists({define})\nSource: "{{#{define}}}\\*"; DestDir: "{{app}}\\{folder}"; Flags: recursesubdirs ignoreversion\n#endif' in iss
        assert f'Type: filesandordirs; Name: "{{app}}\\{folder}"' in iss                  # Replaced on an upgrade, removed on uninstall.
    assert iss.count('Name: "{app}\\python"') == 2 and iss.count('Name: "{app}\\wheelhouse"') == 2
    assert "[InstallDelete]\n#if DirExists(GtkFolder)" in iss                           # The section exists whichever folders do.
    assert "#if DirExists(GtkFolder) && DirExists(PythonFolder) && DirExists(WheelFolder)" in iss     # What the wizard says follows what is inside.


def test_the_installation_check_knows_what_the_install_script_says_when_it_used_the_bundled_parts():
    check = (WINDOWS / "check-installed.ps1").read_text(encoding="utf-8")
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    for marker in ("Python libraries installed from the wheelhouse", "installer that came with KaramTC", "downloading them instead"):
        assert marker in install and marker in check, marker
    assert "Installing Python \\S+ with winget" in check and "Installing Python $Version with winget" in install
    assert "[switch]$ExpectBundledPython" in check
    # Every library the wheelhouse has to hold is looked for in the installed copy.
    assert "'pymupdf', 'pillow', 'faster_whisper', 'ctranslate2', 'av'" in check


def test_ci_checks_that_the_installer_carries_python_and_that_the_first_install_has_no_other_python():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    installer_job = ci.split("  installer:")[1].split("  windows-installer-run:")[0]
    # The libraries are collected with the Python of the GTK runtime, so the job that builds the installer has it.
    assert "actions/setup-python@v5" in installer_job and 'python-version: "3.14"' in installer_job
    carries = installer_job.split("- name: The installer carries the Python installer and the Python libraries")[1].split("- uses:")[0]
    assert "Find-PythonInstaller" in carries and "Test-Wheelhouse 'packaging\\wheelhouse'" in carries and "throw" in carries

    run_job = ci.split("  windows-installer-run:")[1].split("  windows-full-install:")[0]
    first = run_job.split("- name: Run the installer (silently, as a user would, on a machine")[1].split("- name:")[0]
    assert "hostedtoolcache" in first and "PythonCore" in first                       # Neither the PATH nor the registry finds Python.
    assert first.index("PythonCore") < first.index("run-installer.ps1 -Label first")   # Taken away before the installer runs.
    assert "check-installed.ps1 -ExpectBundledPython" in run_job
    upgrade = run_job.split("- name: Check the upgraded installation")[1]
    assert "-ExpectBundledPython" not in upgrade                                       # The upgrade finds Python already there.
    # ... and keeps the Python environment of the first installation instead of making another one.
    assert "'recreating it'" in upgrade and upgrade.index("'recreating it'") < upgrade.index("check-installed.ps1")


def test_the_installers_built_in_ci_must_carry_python_and_the_runtime_or_the_build_says_why():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert ci.count("run: ./packaging/build-windows.ps1 -RequirePython -RequireVcRuntime\n") == 2   # The installer job and windows-installer-run:
    # an installer that quietly lacks Python, its libraries or the Visual C++ runtime would only fail much later.
    assert "run: ./packaging/build-windows.ps1\n" not in ci
