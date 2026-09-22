# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The GTK 4 + libadwaita runtime inside the Windows installer: scripts/gtk-portable.ps1, the build, the install script
and the installer script that carry it, and how the application finds it.

The PowerShell is run with PowerShell 7 (pwsh) where it is installed, on stand-in zips that have the files the install
script looks for; what the real gvsbuild zip looks like on the build machine is what the CI job that builds the installer
(and the manual installer job) check.
"""

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ROOT / "packaging" / "windows"
needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 (pwsh) is not available")


# -- the GTK runtime inside the Windows installer ------------------------------------------------------

def test_the_windows_installer_carries_the_gtk_runtime_when_one_was_prepared():
    text = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    assert "#if DirExists(GtkFolder)" in text and 'DestDir: "{app}\\gtk"' in text
    assert 'gtk-portable.ps1"; DestDir: "{app}\\scripts"' in text                       # The install script needs it.
    # An upgrade replaces the runtime as a whole, so no file of an older one stays beside the new DLLs ...
    assert 'Type: filesandordirs; Name: "{app}\\gtk"' in text.split("[InstallDelete]")[1].split("[Icons]")[0]
    # ... and the uninstaller removes it, with the one an older installer downloaded.
    removed = text.split("[UninstallDelete]")[1].split("[Code]")[0]
    assert '"{app}\\gtk"' in removed and '"{localappdata}\\{#AppId}\\gtk"' in removed


def test_the_build_prepares_the_gtk_runtime_afresh_and_can_pin_it():
    build = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    assert "Get-PortableGtk" in build and "gtk-portable.ps1" in build
    for option in ("NoGtk", "GtkTag", "GtkSha256", "GtkZip"):
        assert f"${option}" in build, option
    assert build.index("Remove-Item $gtkBundle") < build.index("Get-PortableGtk -Target")      # Never an old runtime.
    assert "/packaging/gtk/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_the_install_script_uses_the_runtime_inside_the_installer_before_downloading_one():
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    assert "gtk-portable.ps1" in install and "Resolve-GtkChoice" in install
    assert "function Test-GtkRuntime" not in install              # One definition, in gtk-portable.ps1.
    assert install.index("Resolve-GtkChoice -Explicit") < install.index("Get-PortableGtk -Target $GtkDir")
    assert "$CustomGtk   = $gtkChoice.Custom" in install          # The bundled runtime is found by itself: nothing to save.


def test_the_gtk_download_is_checked_before_it_is_used():
    text = (ROOT / "scripts" / "gtk-portable.ps1").read_text(encoding="utf-8")
    assert "github.com/wingtk/gvsbuild/releases/download/$resolved/$asset" in text
    assert "Get-FileHash" in text and "does not match the expected SHA256" in text
    assert "digest" in text and "gvsbuild-release.txt" in text


GTK_FILES = [
    "bin/gtk-4-1.dll",
    "bin/adwaita-1-0.dll",
    "lib/girepository-1.0/Gtk-4.0.typelib",
    "lib/girepository-1.0/Adw-1.typelib",
    "wheels/PyGObject-3.54.0-cp314-cp314-win_amd64.whl",
    "wheels/pycairo-1.28.0-cp314-cp314-win_amd64.whl",
    "share/glib-2.0/schemas/gschemas.compiled",
]


def make_gtk_zip(path: Path, prefix: str = "", skip: tuple[str, ...] = ()) -> Path:
    """A stand-in for GTK4_Gvsbuild_<tag>_x64.zip: the files the install script looks for, with nothing real in them."""
    with zipfile.ZipFile(path, "w") as archive:
        for name in GTK_FILES:
            if name not in skip:
                archive.writestr(prefix + name, b"x")
    return path


def run_gtk_script(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = tmp_path / "case.ps1"
    script.write_text(f". '{ROOT / 'scripts' / 'gtk-portable.ps1'}'\n{body}\n", encoding="utf-8")
    return subprocess.run(["pwsh", "-NoProfile", "-File", str(script)], capture_output=True, text=True, check=False)


@needs_pwsh
@pytest.mark.parametrize("prefix", ["", "GTK4/"], ids=["at the top", "inside one folder"])
def test_a_gtk_zip_becomes_a_complete_runtime_folder(tmp_path, prefix):
    zip_path = make_gtk_zip(tmp_path / "GTK4_Gvsbuild_2026.8.0_x64.zip", prefix)
    target = tmp_path / "out" / "gtk"
    result = run_gtk_script(tmp_path, f"$ok = Get-PortableGtk -Target '{target}' -ZipPath '{zip_path}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr
    for name in GTK_FILES:
        assert (target / name).is_file(), name
    note = (target / "gvsbuild-release.txt").read_text(encoding="utf-8-sig")
    assert "GTK4_Gvsbuild_2026.8.0_x64.zip" in note and "SHA256 of the zip:" in note
    assert not (tmp_path / "out" / "gtk.partial").exists()


@needs_pwsh
def test_an_incomplete_gtk_zip_is_refused_and_leaves_nothing_behind(tmp_path):
    zip_path = make_gtk_zip(tmp_path / "gtk.zip", skip=("lib/girepository-1.0/Adw-1.typelib",))
    target = tmp_path / "out" / "gtk"
    result = run_gtk_script(tmp_path, f"$ok = Get-PortableGtk -Target '{target}' -ZipPath '{zip_path}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=False" in result.stdout, result.stdout + result.stderr
    assert "not a complete GTK 4" in result.stdout
    assert not target.exists() and not (tmp_path / "out" / "gtk.partial").exists()


@needs_pwsh
def test_a_gtk_zip_must_match_the_hash_it_is_pinned_to(tmp_path):
    import hashlib

    zip_path = make_gtk_zip(tmp_path / "gtk.zip")
    right = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    wrong = ("0" if right[0] != "0" else "1") + right[1:]
    bad = run_gtk_script(tmp_path, f"$ok = Get-PortableGtk -Target '{tmp_path / 'bad'}' -ZipPath '{zip_path}' -Sha256 '{wrong}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=False" in bad.stdout and "does not match the expected SHA256" in bad.stdout, bad.stdout + bad.stderr
    assert not (tmp_path / "bad").exists()
    good = run_gtk_script(tmp_path, f"$ok = Get-PortableGtk -Target '{tmp_path / 'good'}' -ZipPath '{zip_path}' -Sha256 '{right.upper()}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=True" in good.stdout, good.stdout + good.stderr
    assert right.upper() in (tmp_path / "good" / "gvsbuild-release.txt").read_text(encoding="utf-8-sig").upper()


@needs_pwsh
def test_a_complete_runtime_that_is_already_there_is_left_alone(tmp_path):
    target = tmp_path / "gtk"
    for name in GTK_FILES:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(b"mine")
    result = run_gtk_script(tmp_path, f"$ok = Get-PortableGtk -Target '{target}' -ZipPath '{tmp_path / 'does-not-exist.zip'}'\nWrite-Output \"RESULT=$ok\"")
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr
    assert (target / GTK_FILES[0]).read_bytes() == b"mine"


def make_runtime_folder(folder: Path, complete: bool = True) -> Path:
    for name in GTK_FILES:
        if complete or "Adw-1" not in name:
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(b"x")
    return folder


@needs_pwsh
@pytest.mark.parametrize(
    "explicit, bundled, expected_dir, custom, is_bundled",
    [
        ("mine", "complete", "mine", True, False),               # -GtkDir wins, even over a bundled runtime.
        ("default", "complete", "default", False, False),         # ... and naming the default folder is not "custom".
        (None, "complete", "app/gtk", False, True),                # The runtime inside the installer, found by itself.
        (None, "incomplete", "default", False, False),             # A damaged one is not used: the default folder (a download).
        (None, None, "default", False, False),                     # A checkout has none.
    ],
    ids=["explicit", "explicit default", "bundled", "damaged bundle", "none"],
)
def test_which_gtk_runtime_the_install_script_uses(tmp_path, explicit, bundled, expected_dir, custom, is_bundled):
    folders = {"mine": make_runtime_folder(tmp_path / "mine"), "default": tmp_path / "default"}
    folders["default"].mkdir()
    app = tmp_path / "app"
    app.mkdir()
    if bundled:
        make_runtime_folder(app / "gtk", complete=bundled == "complete")
    explicit_path = str(folders[explicit]) if explicit else ""
    body = (
        f"$c = Resolve-GtkChoice -Explicit '{explicit_path}' -ProjectRoot '{app}' -DefaultDir '{folders['default']}'\n"
        "Write-Output \"DIR=$($c.Dir)\"\nWrite-Output \"CUSTOM=$($c.Custom)\"\nWrite-Output \"BUNDLED=$($c.Bundled)\""
    )
    result = run_gtk_script(tmp_path, body)
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(lines["DIR"]) == (tmp_path / expected_dir if expected_dir != "app/gtk" else app / "gtk")
    assert lines["CUSTOM"] == str(custom) and lines["BUNDLED"] == str(is_bundled)


# -- which gvsbuild release, and what a failed installation leaves behind ---------------------------------

def test_the_gtk_release_is_a_tested_one_and_not_the_newest():
    portable = (ROOT / "scripts" / "gtk-portable.ps1").read_text(encoding="utf-8")
    # gvsbuild 2026.10.0 builds its PyGObject wheels for Python 3.15; 2026.8.0 has them for 3.14, which is what CI uses.
    assert "$script:GtkDefaultTag = '2026.8.0'" in portable
    assert "python-version: \"3.14\"" in (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    assert "Get-GtkZipUrls" not in install and "releases/latest" not in install        # No "newest" lookup of its own.
    assert "[string]$GtkTag" in install and "-Tag $GtkTag" in install
    build = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    assert "[string]$GtkTag = ''" in build


@needs_pwsh
@pytest.mark.parametrize("given, expected", [("", "2026.8.0"), ("2026.10.0", "2026.10.0"), ("2026.6.0", "2026.6.0")])
def test_the_gtk_release_is_the_tested_one_unless_another_is_named(tmp_path, given, expected):
    result = run_gtk_script(tmp_path, f"Write-Output \"TAG=$(Resolve-GtkTag '{given}')\"")
    assert f"TAG={expected}" in result.stdout, result.stdout + result.stderr


def test_a_wheel_mismatch_says_which_python_the_wheels_are_for():
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    assert "are for Python $($available -join ', ')" in install and "-GtkTag" in install


def test_the_installer_keeps_a_log_of_the_install_script_and_points_to_it():
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    assert "[string]$LogFile" in install and "Start-Transcript" in install
    iss = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    assert "-LogFile" in iss and "{#AppId}\\install.log" in iss
    assert iss.count("install.log") >= 2                                              # Passed to the script, named in the error.


# -- CI and the installation check ----------------------------------------------------------------------------

def test_ci_checks_that_the_installer_carries_the_gtk_runtime_and_installs_and_upgrades_it():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    installer_job = ci.split("  installer:")[1].split("  windows-installer-run:")[0]
    carries = installer_job.split("- name: The installer carries the GTK runtime")[1].split("- uses:")[0]
    assert "Test-GtkRuntime 'packaging\\gtk'" in carries and "pygobject*.whl" in carries and "throw" in carries
    assert "GITHUB_TOKEN" in installer_job                                # Lifts the API rate limit of the digest lookup.

    run_job = ci.split("  windows-installer-run:")[1].split("  windows-full-install:")[0]
    assert "if: github.event_name == 'workflow_dispatch'" in run_job            # Manual only: it installs everything.
    assert "run-installer.ps1 -Label first" in run_job and "run-installer.ps1 -Label second" in run_job
    assert run_job.count("check-installed.ps1") == 2                              # After the first install and after the upgrade.
    assert "keep-me.txt" in run_job.split("- name: Run the installer again")[0]       # The user's data is there before the upgrade ...
    assert "keep-me.txt" in run_job.split("- name: Check the upgraded installation")[1]   # ... and still there after it.


def test_the_installation_check_looks_for_what_the_installer_and_the_install_script_leave():
    check = (WINDOWS / "check-installed.ps1").read_text(encoding="utf-8")
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    iss = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    marker = "GTK 4 and libadwaita come with the installer"
    assert marker in install and marker in check                                    # What the script says, what the check wants.
    assert "Remove-Item Env:KARAMTC_GTK_DIR" in check                             # Nothing tells the application where GTK is.
    assert "winsupport.prepare_runtime()" in check and "Path(sys.prefix).parent / \"gtk\"" in check
    assert "io.github.AbuKaram01.KaramTC" in check and "install.log" in check
    assert "-LogFile" in iss and "{#AppId}\\install.log" in iss                    # The log the check (and the CI job) read.
    runner = (WINDOWS / "run-installer.ps1").read_text(encoding="utf-8")
    assert "/VERYSILENT" in runner and "install.log" in runner and "io.github.AbuKaram01.KaramTC" in runner


def test_the_application_looks_for_the_runtime_where_the_installer_puts_it():
    iss = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    winsupport = (ROOT / "src" / "winsupport.py").read_text(encoding="utf-8")
    assert 'DestDir: "{app}\\gtk"' in iss                                            # <application folder>\gtk ...
    assert 'os.path.join(application_folder(), "gtk")' in winsupport                  # ... is where winsupport looks (beside .venv).
    assert 'DestDir: "{app}\\src"' in iss and 'DefaultDirName={localappdata}\\Programs\\{#AppName}' in iss


def test_the_install_script_hands_the_named_folder_to_the_choice():
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    # -GtkDir has to reach Resolve-GtkChoice, or it would never win over the runtime inside the installer.
    assert "Resolve-GtkChoice -Explicit $GtkDir -ProjectRoot $ProjectRoot -DefaultDir $DefaultGtk" in install
    assert "$gtkExplicit = [bool]$GtkDir" in install


def test_the_uninstall_script_removes_the_runtime_the_installer_carried_only_when_it_is_one():
    uninstall = (ROOT / "scripts" / "uninstall-windows.ps1").read_text(encoding="utf-8")
    assert "$carriedGtk = Join-Path $ProjectRoot 'gtk'" in uninstall
    # A folder called gtk that the installer did not make (no release note in it) is not touched.
    assert "if (Test-Path (Join-Path $carriedGtk 'gvsbuild-release.txt')) { Remove-IfPresent $carriedGtk }" in uninstall
