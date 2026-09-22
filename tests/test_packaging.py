# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Checks on the Arch installation files: versions agree, scripts parse, the installer and the
package build do the right steps.

The installer and the build refuse to run as root (as they should), so the tests that run them are
skipped for root. makepkg, pacman and Python's venv are replaced by stand-ins that only record what
they are asked.
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import config

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "packaging" / "arch"
APP_ID = "io.github.AbuKaram01.KaramTC"
SCRIPTS = [
    ROOT / "packaging" / "build.sh",
    ROOT / "packaging" / "build-arch.sh",
    ROOT / "scripts" / "install-debian.sh",
    ROOT / "scripts" / "install-arch.sh",
]

def running_as_root() -> bool:
    return sys.platform != "win32" and os.geteuid() == 0


# The shell scripts and their stand-ins are POSIX-only (":"-separated PATH, /bin/sh), so they are skipped on Windows.
needs_bash = pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32", reason="needs bash on a POSIX system",
)
not_root = pytest.mark.skipif(running_as_root(), reason="the installer refuses to run as root")
needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 (pwsh) is not available")
WINDOWS = ROOT / "packaging" / "windows"
POWERSHELL_SCRIPTS = [
    ROOT / "scripts" / "install-windows.ps1",
    ROOT / "scripts" / "uninstall-windows.ps1",
    ROOT / "packaging" / "build-windows.ps1",
    ROOT / "scripts" / "tesseract-portable.ps1",
    ROOT / "scripts" / "gtk-portable.ps1",
    ROOT / "scripts" / "python-bundle.ps1",
    ROOT / "scripts" / "vcruntime-bundle.ps1",
    ROOT / "packaging" / "windows" / "check-installed.ps1",
    ROOT / "packaging" / "windows" / "run-installer.ps1",
]


def pkgbuild_value(name):
    match = re.search(rf"^{name}=(.+)$", (ARCH / "PKGBUILD").read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1).strip("'\"") if match else None


def make_executable(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


# -- static checks ---------------------------------------------------------------------------------

def test_the_pkgbuild_version_matches_the_app_version():
    assert pkgbuild_value("pkgver") == config.VERSION


def test_the_pkgbuild_builds_one_architecture_independent_package():
    text = (ARCH / "PKGBUILD").read_text(encoding="utf-8")
    assert "pkgname=karamtc\n" in text
    assert "arch=('any')" in text                              # Pure Python: nothing is compiled.
    assert "install=karamtc.install" in text


def test_the_pkgbuild_builds_from_a_release_style_tarball_so_it_can_go_to_the_aur():
    """GitHub names the folder inside a release archive after the repository (KaramTC-0.1.0, not karamtc-0.1.0)."""
    text = (ARCH / "PKGBUILD").read_text(encoding="utf-8")
    assert '_srcdir="KaramTC-$pkgver"' in text
    assert "/archive/v$pkgver.tar.gz" in text and "sha256sums=('SKIP')" in text
    assert "$startdir/.." not in text                         # No reaching into the local checkout.


def test_the_pkgbuild_depends_on_what_the_app_needs_at_run_time():
    text = (ARCH / "PKGBUILD").read_text(encoding="utf-8")
    for package in ("python", "python-gobject", "gtk4", "libadwaita", "librsvg", "adwaita-icon-theme",
                    "python-pymupdf", "python-pillow", "tesseract", "tesseract-data-eng",
                    "tesseract-data-ara", "tesseract-data-osd"):
        assert re.search(rf"^\s*'{re.escape(package)}[>=<']", text, re.MULTILINE), package


def test_the_pkgbuild_requires_the_libadwaita_version_the_app_checks_for_at_start_up():
    main = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
    major, minor = re.search(r"MIN_LIBADWAITA = \((\d+), (\d+)\)", main).groups()
    assert f"'libadwaita>={major}.{minor}'" in (ARCH / "PKGBUILD").read_text(encoding="utf-8")


def test_the_install_script_defines_the_pacman_hooks_it_uses():
    content = (ARCH / "karamtc.install").read_text(encoding="utf-8")
    assert "post_install()" in content and "post_remove()" in content
    assert "rm -rf /opt/karamtc" in content


@needs_bash
def test_the_install_script_points_at_the_pip_command_for_the_audio_video_tab():
    result = subprocess.run(
        ["bash", "-c", f'source "{ARCH / "karamtc.install"}"; post_install'],
        capture_output=True, text=True, check=True,
    )
    assert "faster-whisper" in result.stdout


@needs_bash
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_every_shell_script_parses(script):
    assert script.exists()
    subprocess.run(["bash", "-n", str(script)], check=True)


@needs_bash
def test_the_pkgbuild_parses_and_defines_the_check_and_package_functions():
    result = subprocess.run(
        ["bash", "-c", f'source "{ARCH / "PKGBUILD"}"; declare -F check package'],
        capture_output=True, text=True, check=True,
    )
    assert sorted(result.stdout.split()) == ["check", "package"]


def test_the_desktop_entry_has_the_placeholder_the_installers_fill_in_and_the_app_icon():
    entry = (ROOT / "data" / f"{APP_ID}.desktop").read_text(encoding="utf-8")
    assert "Exec=karamtc-exec-placeholder" in entry and f"Icon={APP_ID}" in entry


def test_the_license_file_is_present():
    assert "GNU AFFERO GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_the_build_scripts_read_the_version_from_the_app_and_do_not_delete_each_others_packages():
    """build.sh and build-arch.sh share packaging/dist; neither may wipe the whole folder."""
    for script in ("build.sh", "build-arch.sh"):
        text = (ROOT / "packaging" / script).read_text(encoding="utf-8")
        assert "src/config.py" in text, script
        assert 'rm -rf "$OUT_DIR"' not in text and 'rm -rf "$WORK_DIR" "$OUT_DIR"' not in text, script


def test_the_deb_is_architecture_independent_like_the_rpm_and_the_arch_package():
    """The app is pure Python, so the .deb must say `all` (not amd64) and install on ARM machines too."""
    text = (ROOT / "packaging" / "build.sh").read_text(encoding="utf-8")
    assert "Architecture: all" in text and "karamtc_${VERSION}_all.deb" in text
    assert "Architecture: amd64" not in text
    assert "arch=('any')" in (ARCH / "PKGBUILD").read_text(encoding="utf-8")


def test_build_sh_leaves_the_arch_package_to_build_arch_sh():
    text = (ROOT / "packaging" / "build.sh").read_text(encoding="utf-8")
    assert "packaging/build-arch.sh" in text
    assert "makepkg -f" not in text                            # No second, hand-rolled makepkg run.
    assert not (ROOT / "packaging" / "PKGBUILD").exists()      # The PKGBUILD lives in packaging/arch/.


# -- scripts/install-arch.sh, with pacman and python stood in for ----------------------------------------

class Checkout:
    """A throwaway project folder holding a copy of install-arch.sh and the data files it installs."""

    def __init__(self, tmp_path):
        self.root = tmp_path / "KaramTC"
        (self.root / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "scripts" / "install-arch.sh", self.root / "scripts")
        shutil.copytree(ROOT / "data", self.root / "data")
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.log = tmp_path / "calls.log"
        self.log.touch()
        bin_dir = tmp_path / "stubs"
        bin_dir.mkdir()
        make_executable(bin_dir / "pacman", f'#!/bin/sh\necho "pacman $*" >> "{self.log}"\n')
        make_executable(bin_dir / "sudo", '#!/bin/sh\nexec "$@"\n')
        make_executable(bin_dir / "gtk-update-icon-cache", "#!/bin/sh\nexit 0\n")
        make_executable(bin_dir / "python3", f"""#!/bin/sh
case "$1" in
    -c) echo 3.13; exit 0 ;;
    -m) DIR="$4"
        echo "venv $DIR" >> "{self.log}"
        mkdir -p "$DIR/bin"
        printf 'version = 3.13.1\\n' > "$DIR/pyvenv.cfg"
        cat > "$DIR/bin/pip" <<'PIP'
#!/bin/sh
echo "pip $*" >> "{self.log}"
PIP
        chmod +x "$DIR/bin/pip" ;;
esac
""")
        self.env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(self.home)}

    def run(self, *arguments):
        result = subprocess.run(
            ["bash", str(self.root / "scripts" / "install-arch.sh"), *arguments],
            env=self.env, capture_output=True, text=True, cwd=self.root,
        )
        return result, self.log.read_text(encoding="utf-8").splitlines()


@needs_bash
@not_root
def test_the_installer_installs_the_system_packages_and_then_the_python_requirements(tmp_path):
    checkout = Checkout(tmp_path)
    result, calls = checkout.run()
    assert result.returncode == 0, result.stderr

    pacman = next(call for call in calls if call.startswith("pacman"))
    assert pacman.startswith("pacman -S --needed --noconfirm")
    for package in ("python-pip", "python-gobject", "gtk4", "libadwaita", "librsvg", "adwaita-icon-theme",
                    "tesseract", "tesseract-data-eng", "tesseract-data-ara", "tesseract-data-osd"):
        assert re.search(rf"\b{package}\b", pacman), package
    assert calls[-2:] == ["pip install --upgrade pip -q", "pip install -r requirements.txt -q"]


@needs_bash
@not_root
def test_the_installer_registers_the_launcher_with_an_absolute_path(tmp_path):
    checkout = Checkout(tmp_path)
    checkout.run()
    entry = (checkout.home / ".local" / "share" / "applications" / f"{APP_ID}.desktop").read_text()
    assert f"Exec={checkout.root}/.venv/bin/python3 {checkout.root}/src/main.py" in entry
    assert "karamtc-exec-placeholder" not in entry
    assert (checkout.home / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg").is_file()


@needs_bash
@not_root
def test_an_environment_from_an_older_python_is_started_over(tmp_path):
    checkout = Checkout(tmp_path)
    (checkout.root / ".venv").mkdir()
    (checkout.root / ".venv" / "pyvenv.cfg").write_text("version = 3.12.4\n")
    _result, calls = checkout.run()
    assert any(call.startswith("venv ") for call in calls)


@needs_bash
@not_root
def test_an_environment_of_the_same_python_is_reused(tmp_path):
    checkout = Checkout(tmp_path)
    (checkout.root / ".venv").mkdir()
    (checkout.root / ".venv" / "pyvenv.cfg").write_text("version = 3.13.1\n")
    (checkout.root / ".venv" / "bin").mkdir()
    make_executable(checkout.root / ".venv" / "bin" / "pip", f'#!/bin/sh\necho "pip $*" >> "{checkout.log}"\n')
    _result, calls = checkout.run()
    assert not any(call.startswith("venv ") for call in calls)
    assert calls[-1] == "pip install -r requirements.txt -q"


@needs_bash
def test_an_unknown_option_is_refused_and_help_needs_no_pacman():
    script = ROOT / "scripts" / "install-arch.sh"
    refused = subprocess.run(["bash", str(script), "--nope"], capture_output=True, text=True)
    assert refused.returncode != 0 and "Unknown option" in refused.stderr
    helped = subprocess.run(["bash", str(script), "--help"], capture_output=True, text=True)
    assert helped.returncode == 0 and "install-arch.sh" in helped.stdout


@needs_bash
def test_the_installer_refuses_a_system_without_pacman(tmp_path):
    """PATH holds only dirname, so the script can't find a real pacman even on an Arch machine."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "dirname").symlink_to(shutil.which("dirname"))
    result = subprocess.run(
        [shutil.which("bash"), str(ROOT / "scripts" / "install-arch.sh")],
        env={"PATH": str(bin_dir), "HOME": str(tmp_path)}, capture_output=True, text=True,
    )
    assert result.returncode != 0 and "needs pacman" in result.stderr


# -- packaging/build-arch.sh, with makepkg stood in for ----------------------------------------------------

FAKE_MAKEPKG = r"""#!/usr/bin/env bash
# Does the parts of makepkg that matter here: unpack the source, then run check() and package().
set -euo pipefail
echo "makepkg $*" >> "$FAKE_LOG"
startdir="$PWD"
srcdir="$startdir/src"
mkdir -p "$srcdir"
source ./PKGBUILD
tar -xzf "$SRCDEST/$pkgname-$pkgver.tar.gz" -C "$srcdir"
check
pkgdir="$startdir/pkg/$pkgname"
mkdir -p "$pkgdir"
package
: > "$PKGDEST/$pkgname-$pkgver-$pkgrel-any.pkg.tar.zst"
"""


@pytest.fixture
def built(tmp_path):
    """A copy of the project built by build-arch.sh with the stand-in makepkg."""
    if running_as_root():
        pytest.skip("makepkg, and so build-arch.sh, refuses to run as root")
    project = tmp_path / "project"
    shutil.copytree(
        ROOT, project,
        ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "work"),
    )
    (project / ".git").mkdir()                                  # Must be left out of the tarball.
    (project / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    bin_dir = tmp_path / "stubs"
    bin_dir.mkdir()
    make_executable(bin_dir / "makepkg", FAKE_MAKEPKG)
    make_executable(bin_dir / "python", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')   # check() runs `python`.
    log = tmp_path / "makepkg.log"
    log.touch()
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(log)}
    result = subprocess.run(
        ["bash", str(project / "packaging" / "build-arch.sh"), "--noconfirm"],
        env=env, capture_output=True, text=True, cwd=project,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return project, log


@needs_bash
def test_build_arch_makes_a_github_style_tarball_and_the_package(built):
    project, log = built
    version = config.VERSION
    work = project / "packaging" / "work" / "arch"

    names = tarfile.open(work / f"karamtc-{version}.tar.gz").getnames()
    assert all(name.startswith(f"KaramTC-{version}") for name in names)         # One top-level folder.
    assert f"KaramTC-{version}/packaging/arch/PKGBUILD" in names
    assert f"KaramTC-{version}/packaging/arch/karamtc.install" in names
    assert f"KaramTC-{version}/src/main.py" in names
    leftovers = {".git", "__pycache__", ".ruff_cache", ".pytest_cache"}
    assert not any(leftovers & set(Path(name).parts) for name in names)          # (.gitignore itself is fine.)
    assert f"KaramTC-{version}/.gitignore" in names
    assert not any(name.startswith(f"KaramTC-{version}/packaging/work") for name in names)

    dist = project / "packaging" / "dist"
    assert [path.name for path in dist.iterdir()] == [f"karamtc-{version}-1-any.pkg.tar.zst"]
    assert "--noconfirm" in log.read_text() and "--cleanbuild" in log.read_text()


@needs_bash
def test_the_arch_package_contains_the_app_launcher_desktop_file_icon_and_license(built):
    project, _log = built
    pkg = project / "packaging" / "work" / "arch" / "pkg" / "karamtc"
    app = pkg / "opt" / "karamtc"

    for name in ("main.py", "config.py", "settings.py", "core/__init__.py", "providers/registry.py",
                 "providers/tesseract/engine.py", "ui/app.py", "ui/main_window.py"):
        assert (app / name).is_file(), name
    assert not list(pkg.rglob("__pycache__"))
    assert not (app / "tests").exists() and not (app / ".git").exists() and not list(pkg.rglob(".ruff_cache"))

    launcher = pkg / "usr/bin/karamtc"
    text = launcher.read_text()
    assert launcher.stat().st_mode & 0o111 and "exec python3 /opt/karamtc/main.py" in text
    assert "PYTHONDONTWRITEBYTECODE=1" in text

    entry = (pkg / f"usr/share/applications/{APP_ID}.desktop").read_text()
    assert re.search(r"^Exec=karamtc$", entry, re.MULTILINE) and "placeholder" not in entry
    assert (pkg / f"usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg").is_file()
    assert (pkg / "usr/share/licenses/karamtc/LICENSE").is_file()


@needs_bash
def test_the_arch_package_installs_files_with_normal_permissions(built):
    project, _log = built
    app = project / "packaging" / "work" / "arch" / "pkg" / "karamtc" / "opt" / "karamtc"
    assert (app / "main.py").stat().st_mode & 0o777 == 0o644
    assert (app / "ui").stat().st_mode & 0o777 == 0o755


@needs_bash
def test_build_arch_refuses_a_pkgbuild_whose_version_differs_from_the_app(tmp_path):
    if running_as_root():
        pytest.skip("makepkg, and so build-arch.sh, refuses to run as root")
    project = tmp_path / "project"
    (project / "packaging" / "arch").mkdir(parents=True)
    (project / "src").mkdir()
    shutil.copy(ROOT / "packaging" / "build-arch.sh", project / "packaging")
    (project / "src" / "config.py").write_text('VERSION  = "9.9.9"\n')
    (project / "packaging" / "arch" / "PKGBUILD").write_text("pkgver=0.1.0\n")
    result = subprocess.run(["bash", str(project / "packaging" / "build-arch.sh")], capture_output=True, text=True)
    assert result.returncode != 0 and "Version mismatch" in result.stderr


# -- Windows ------------------------------------------------------------------------------------

def test_the_windows_icon_and_installer_files_exist():
    assert (ROOT / "data" / "windows" / "karamtc.ico").is_file()
    assert (WINDOWS / "karamtc.iss").is_file()
    for script in POWERSHELL_SCRIPTS:
        assert script.is_file(), script


def test_the_installer_script_matches_the_app_version_and_id():
    text = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    assert f'#define AppVersion "{config.VERSION}"' in text
    assert f'#define AppId "{APP_ID}"' in text
    assert config.APP_ID == APP_ID


def test_the_installer_runs_the_install_script_per_user_and_cleans_up_after_itself():
    text = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in text
    assert "scripts\\install-windows.ps1" in text and "-NoShortcut" in text
    assert "{app}\\.venv" in text and "{localappdata}\\{#AppId}\\gtk" in text
    assert "src\\main.py" in text                                  # The shortcut runs the script, not a module.
    assert "requirements.txt" in text                              # What the install script installs from.
    deletions = [
        line.lower() for line in text.split("[UninstallDelete]")[1].split("[Code]")[0].splitlines()
        if line.strip() and not line.startswith(";")
    ]
    for kept in ("models", "tessdata", "settings", "config", "appdata\\roaming"):
        assert not any(kept in line for line in deletions), kept          # User data is never deleted.


def test_the_install_script_follows_the_runtime_that_the_application_looks_for():
    text = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    portable = (ROOT / "scripts" / "gtk-portable.ps1").read_text(encoding="utf-8")      # Where Test-GtkRuntime lives.
    assert "$AppId" in text and "io.github.AbuKaram01.KaramTC" in text      # GLib's data folder, see winsupport.
    assert "KARAMTC_GTK_DIR" in text and "src\\main.py" in text
    assert "Adw-1.typelib" in portable
    assert "*adwaita-1-*.dll" in portable                     # The DLL is adwaita-1-0.dll, not libadwaita-...
    assert "UB-Mannheim.TesseractOCR" in text                 # The OCR program is installed with the rest.
    assert "requirements.txt" in text


@pytest.mark.parametrize("name", ["install-windows.ps1", "uninstall-windows.ps1"])
def test_the_windows_scripts_refuse_to_run_elsewhere_with_a_clear_message(name):
    text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
    assert "$env:OS -ne 'Windows_NT'" in text and "install-debian.sh" in text
    # The check has to come before anything that needs Windows.
    assert text.index("Windows_NT") < text.index("$env:LOCALAPPDATA")


@needs_pwsh
@pytest.mark.parametrize("script", POWERSHELL_SCRIPTS, ids=lambda path: path.name)
def test_every_powershell_script_parses(script, tmp_path):
    checker = tmp_path / "parse.ps1"
    checker.write_text(
        "param($Path)\n"
        "$errors = $null; $tokens = $null\n"
        "[System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors) | Out-Null\n"
        "if ($errors.Count) { $errors | ForEach-Object { Write-Output $_.Message }; exit 1 }\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(checker), str(script)], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout


def test_the_build_script_reads_the_version_from_config_py():
    text = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    assert "src\\config.py" in text and "VERSION" in text
    assert re.search(r'(?m)^VERSION\s*=\s*"[^"]+"', (ROOT / "src" / "config.py").read_text(encoding="utf-8"))

def test_the_windows_installer_carries_a_portable_tesseract_when_one_was_prepared():
    text = (WINDOWS / "karamtc.iss").read_text(encoding="utf-8")
    assert "#if DirExists(TesseractFolder)" in text and 'DestDir: "{app}\\tesseract"' in text
    assert 'tesseract-portable.ps1"; DestDir: "{app}\\scripts"' in text                # The install script needs it.
    assert "\\tesseract\"" in text.split("[UninstallDelete]")[1]                         # The fetched copy is removed.


def test_the_portable_tesseract_is_pinned_and_checked():
    text = (ROOT / "scripts" / "tesseract-portable.ps1").read_text(encoding="utf-8")
    assert "$script:TesseractVersion = '5.4.0.20240606'" in text
    assert "github.com/UB-Mannheim/tesseract/releases/download/v$($script:TesseractVersion)/" in text
    assert "C885FFF6998E0608BA4BB8AB51436E1C6775C2BAFC2559A19B423E18678B60C9" in text      # Published by winget.
    assert "Get-FileHash" in text and "does not match the published SHA256" in text
    for needed in ("tesseract.exe", "libtesseract-5.dll", "libleptonica-6.dll", "libstdc++-6.dll", "libgcc_s_seh-1.dll"):
        assert f"'{needed}'" in text, needed
    for data in ("eng.traineddata", "osd.traineddata", "pdf.ttf", "configs", "tessconfigs"):
        assert f"'{data}'" in text, data
    assert "'doc'" in text                                      # The license notices travel with the copy.


def test_the_scripts_use_the_portable_tesseract_before_winget():
    install = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    assert "tesseract-portable.ps1" in install
    assert install.index("Get-PortableTesseract") < install.index("winget install --id UB-Mannheim.TesseractOCR")
    assert "'tesseract\\tesseract.exe'" in install                                        # Found beside the program.
    build = (ROOT / "packaging" / "build-windows.ps1").read_text(encoding="utf-8")
    assert "NoTesseract" in build and "Get-PortableTesseract" in build
    assert "/packaging/tesseract/" in (ROOT / ".gitignore").read_text(encoding="utf-8")

