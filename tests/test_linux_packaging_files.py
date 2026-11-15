# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The Linux packaging files: the PKGBUILD, the install hooks, the desktop entry and the build scripts.

These are static checks on text and on shell syntax. The scripts that do the work are run in test_install_arch.py and
test_build_arch.py.
"""

import re
import subprocess

import pytest

import config
from packaging_support import APP_ID, ARCH, ROOT, needs_bash

SHELL_SCRIPTS = [
    ROOT / "packaging" / "build.sh",
    ROOT / "packaging" / "build-arch.sh",
    ROOT / "scripts" / "install-debian.sh",
    ROOT / "scripts" / "install-arch.sh",
]


def pkgbuild_value(name):
    """The value of ``name`` in packaging/arch/PKGBUILD, without its quotes, or None."""
    match = re.search(rf"^{name}=(.+)$", (ARCH / "PKGBUILD").read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1).strip("'\"") if match else None


def test_the_pkgbuild_version_matches_the_app_version():
    assert pkgbuild_value("pkgver") == config.VERSION


def test_the_pkgbuild_builds_one_architecture_independent_package():
    text = (ARCH / "PKGBUILD").read_text(encoding="utf-8")
    assert "pkgname=karamtc\n" in text
    assert "arch=('any')" in text  # Pure Python: nothing is compiled.
    assert "install=karamtc.install" in text


def test_the_pkgbuild_builds_from_a_release_style_tarball_so_it_can_go_to_the_aur():
    """GitHub names the folder inside a release archive after the repository (KaramTC-0.1.0, not karamtc-0.1.0)."""
    text = (ARCH / "PKGBUILD").read_text(encoding="utf-8")
    assert '_srcdir="KaramTC-$pkgver"' in text
    assert "/archive/v$pkgver.tar.gz" in text and "sha256sums=('SKIP')" in text
    assert "$startdir/.." not in text  # No reaching into the local checkout.


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
@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda path: path.name)
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
    assert "makepkg -f" not in text  # No second, hand-rolled makepkg run.
    assert not (ROOT / "packaging" / "PKGBUILD").exists()  # The PKGBUILD lives in packaging/arch/.
