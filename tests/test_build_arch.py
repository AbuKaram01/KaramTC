# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""packaging/build-arch.sh, run with makepkg replaced by a stand-in that unpacks the source and runs check and package.

The build refuses to run as root, so these tests are skipped for root.
"""

import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import config
from packaging_support import APP_ID, ROOT, make_executable, needs_bash, running_as_root


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
    (project / ".git").mkdir()  # Must be left out of the tarball.
    (project / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    bin_dir = tmp_path / "stubs"
    bin_dir.mkdir()
    make_executable(bin_dir / "makepkg", FAKE_MAKEPKG)
    make_executable(bin_dir / "python", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')  # check() runs `python`.
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
    assert all(name.startswith(f"KaramTC-{version}") for name in names)  # One top-level folder.
    assert f"KaramTC-{version}/packaging/arch/PKGBUILD" in names
    assert f"KaramTC-{version}/packaging/arch/karamtc.install" in names
    assert f"KaramTC-{version}/src/main.py" in names
    leftovers = {".git", "__pycache__", ".ruff_cache", ".pytest_cache"}
    assert not any(leftovers & set(Path(name).parts) for name in names)  # (.gitignore itself is fine.)
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
