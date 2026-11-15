# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""scripts/install-arch.sh, run with pacman, sudo and python replaced by stand-ins that only record what they are asked.

The installer refuses to run as root, so these tests are skipped for root.
"""

import os
import re
import shutil
import subprocess

from packaging_support import APP_ID, ROOT, make_executable, needs_bash, not_root


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
