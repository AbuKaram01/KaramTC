#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""KaramTC application entry point."""

from __future__ import annotations

import sys

if sys.platform == "win32":
    # This has to run before GTK is loaded. prepare_runtime() tells Python where the DLLs of the GTK runtime are.
    # log_errors_without_a_console() keeps the errors of a start without a console (pythonw.exe, the Start menu
    # entry) in karamtc.log instead of losing them.
    import winsupport

    winsupport.log_errors_without_a_console()
    winsupport.prepare_runtime()

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw

# The UI uses the dialog widgets of libadwaita (Adw.PreferencesDialog, AlertDialog, AboutDialog and others), which
# were added in version 1.5. On an older version the application would otherwise fail on import with an unhelpful
# AttributeError.
MIN_LIBADWAITA = (1, 5)


def check_libadwaita(version: tuple[int, int] | None = None) -> None:
    """Exit with an explanatory message when libadwaita is older than MIN_LIBADWAITA.

    Args:
        version: The (major, minor) version to check. Defaults to the version of the loaded libadwaita.
    """
    found = version or (Adw.get_major_version(), Adw.get_minor_version())
    if found < MIN_LIBADWAITA:
        sys.stderr.write(
            "KaramTC needs libadwaita {}.{} or newer, but this system has {}.{}.\n"
            "Please upgrade your system (or install a newer libadwaita) and try again.\n".format(
                *MIN_LIBADWAITA, *found
            )
        )
        sys.exit(1)


check_libadwaita()

from ui.app import OcrApp


if __name__ == "__main__":
    app = OcrApp()
    sys.exit(app.run(sys.argv))
