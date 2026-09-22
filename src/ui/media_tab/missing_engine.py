# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/media_tab/missing_engine.py — Shown instead of the tab when faster-whisper is not installed.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from ui.widgets import centered_row, command_row, pill_button, scrolled_clamp, status_page

# PyAV 19 removed an argument faster-whisper 1.2 still passes when it opens
# audio, so the newest PyAV breaks decoding until faster-whisper catches up.
_PACKAGES = '"faster-whisper>=1.1,<2" "av>=11,<19"'
INSTALL_COMMANDS = [
    ("From a source checkout", f".venv/bin/pip install {_PACKAGES}"),
    ("Installed from a package", f"pip install --user --break-system-packages {_PACKAGES}"),
    ("Any Python environment", f"pip install {_PACKAGES}"),
]


def build_engine_missing_page(on_recheck) -> Gtk.ScrolledWindow:
    scroll, clamp = scrolled_clamp(maximum_size=580, tightening_threshold=400)
    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    clamp.set_child(content)

    content.append(status_page(
        "audio-x-generic-symbolic", "The speech engine isn’t installed",
        "Turning audio and video into text needs the faster-whisper package.\n"
        "Install it with one of the commands below, then check again.",
    ))
    group = Adw.PreferencesGroup()
    group.set_title("Install commands")
    for title, command in INSTALL_COMMANDS:
        group.add(command_row(title, command))
    content.append(group)
    content.append(centered_row(pill_button("Check again", "view-refresh-symbolic", lambda *_: on_recheck())))
    return scroll
