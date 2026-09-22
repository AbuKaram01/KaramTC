# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/app.py — OcrApp: the top-level GTK/Adwaita application class.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from config import APP_ID, APP_NAME, VERSION
from providers import tesseract
from ui.main_window import OcrWindow


class OcrApp(Adw.Application):

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.connect("activate", self._on_activate)
        self.connect("shutdown", self._on_shutdown)

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])
        self.set_accels_for_action("win.ocr-settings", ["<primary>comma"])

    def _on_activate(self, app):
        # Launching the app again (e.g. clicking its icon while it is already
        # open) activates this same process: bring the existing window forward
        # instead of opening a second, independent one.
        window = app.get_active_window() or OcrWindow(application=app)
        window.present()

    def _on_shutdown(self, *_):
        # Quitting with Ctrl+Q closes no window, so the window never gets its close request:
        # remember where the user left it here as well.
        for window in self.get_windows():
            if isinstance(window, OcrWindow):
                window.save_window_state()
        # Don't leave Tesseract processes running after the app has quit.
        tesseract.terminate_active_processes()

    def _on_about(self, *_):
        Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon=APP_ID,
            version=VERSION,
            developer_name="AbuKaram01",
            comments="Copy text out of images and PDF files, powered by Tesseract OCR",
            license_type=Gtk.License.AGPL_3_0,
            developers=["AbuKaram01"],
        ).present(self.get_active_window())
