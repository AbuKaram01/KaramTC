# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/install_warning.py — Shown instead of the tabs when Tesseract is not installed.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ui.widgets import command_row, scrolled_clamp, status_page

INSTALL_COMMANDS = [
    ("Ubuntu / Debian", "sudo apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng"),
    ("Fedora",          "sudo dnf install tesseract tesseract-langpack-ara"),
    ("Arch",            "sudo pacman -S tesseract tesseract-data-ara tesseract-data-eng"),
    ("macOS",           "brew install tesseract tesseract-lang"),
    ("Windows",         "winget install UB-Mannheim.TesseractOCR"),
]


def build_install_warning_page() -> Gtk.ScrolledWindow:
    scroll, clamp = scrolled_clamp(maximum_size=580, tightening_threshold=400)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    clamp.set_child(content)

    content.append(status_page(
        "dialog-warning-symbolic", "Tesseract is not installed",
        "Install Tesseract to start extracting text from images and PDFs",
    ))
    group = Adw.PreferencesGroup()
    group.set_title("Install commands")
    for distro, command in INSTALL_COMMANDS:
        group.add(command_row(distro, command))
    content.append(group)
    return scroll
