# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract/install.py — Is Tesseract installed, and how to install it.
"""
from __future__ import annotations

import shutil
from typing import NamedTuple

from providers.tesseract import program


def is_installed() -> bool:
    """True if the 'tesseract' binary is on the system PATH (or, on Windows, in its installer's folder)."""
    return (
        shutil.which("tesseract") is not None
        or program.bundled_path() is not None
        or program.windows_install_path() is not None
    )


class _PackageManager(NamedTuple):
    executable: str         # looked up on PATH to detect the package manager
    install_tesseract: str
    install_language: str   # template; "{lang}" is replaced when present
    install_osd: str


# Checked in order; the first package manager found on PATH wins. Language
# pack and osd package names are verified per distro: Fedora's osd package is
# "tesseract-osd" (not "tesseract-langpack-osd"), and Homebrew's base formula
# already bundles eng + osd while "tesseract-lang" installs every language.
# Package managers with less predictable names (zypper, …) are deliberately
# absent: a wrong guess is worse than a generic pointer.
_PACKAGE_MANAGERS = [
    _PackageManager("apt", "sudo apt install tesseract-ocr",
                    "sudo apt install tesseract-ocr-{lang}", "sudo apt install tesseract-ocr-osd"),
    _PackageManager("dnf", "sudo dnf install tesseract",
                    "sudo dnf install tesseract-langpack-{lang}", "sudo dnf install tesseract-osd"),
    _PackageManager("pacman", "sudo pacman -S tesseract",
                    "sudo pacman -S tesseract-data-{lang}", "sudo pacman -S tesseract-data-osd"),
    _PackageManager("brew", "brew install tesseract",
                    "brew install tesseract-lang", "brew install tesseract"),
    # Windows: the UB Mannheim build. Its installer brings English and the orientation data (osd); the other
    # languages are downloaded in OCR Settings, so every command here is the program's own.
    _PackageManager("winget", "winget install UB-Mannheim.TesseractOCR",
                    "winget install UB-Mannheim.TesseractOCR", "winget install UB-Mannheim.TesseractOCR"),
]


def _detect_package_manager() -> _PackageManager | None:
    return next((pm for pm in _PACKAGE_MANAGERS if shutil.which(pm.executable)), None)


def install_hint(lang: str | None = None) -> str:
    """
    One-line command to install Tesseract itself (lang=None) or a single
    language pack (lang="ara", say), using the package manager detected on
    this machine.
    """
    manager = _detect_package_manager()
    if manager is None:
        return "Install Tesseract using whatever package manager your system provides."
    if lang is None:
        return f"Run: {manager.install_tesseract}"
    return f"Run: {manager.install_language.format(lang=lang)}"


def osd_install_hint() -> str:
    """One-line command to install the orientation/script data file (osd)."""
    manager = _detect_package_manager()
    if manager is None:
        return "Install the Tesseract orientation data (osd) using your system's package manager."
    return f"Run: {manager.install_osd}"
