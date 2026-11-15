# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""What the tests of the installation files share.

That is where the project is, which tools a test needs, and how to make a stand-in program.
"""

import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARCH = ROOT / "packaging" / "arch"
WINDOWS = ROOT / "packaging" / "windows"
APP_ID = "io.github.AbuKaram01.KaramTC"


def running_as_root() -> bool:
    """Whether the tests run as root, which the installer and the package build refuse."""
    return sys.platform != "win32" and os.geteuid() == 0


# The shell scripts and their stand-ins are POSIX-only (":"-separated PATH, /bin/sh), so they are skipped on Windows.
needs_bash = pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="needs bash on a POSIX system",
)
not_root = pytest.mark.skipif(running_as_root(), reason="the installer refuses to run as root")
needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell 7 (pwsh) is not available")


def make_executable(path: Path, text: str) -> Path:
    """Write ``text`` to ``path``, make the file executable and return the path."""
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path
