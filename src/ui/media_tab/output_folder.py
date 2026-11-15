# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Where the transcript is saved.

By default the transcript goes next to the media file. The user can pick a folder instead, which is then
remembered for every file until it is reset.
"""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

import settings as app_settings
from ui import file_dialogs, saved_settings
from ui.widgets import flat_icon_button, flat_text_button, make_icon_prefix

_RESET_TOOLTIP = "Stop remembering this folder — save next to each file again"
_NEXT_TO_FILE = "Next to the file"


class OutputFolder:
    """The output-folder row and the choice behind it.

    Args:
        get_parent: Returns the window that dialogs should open over.
        show_toast: Shows a short message to the user.
        on_changed: Called when the user picks or resets the folder.

    Attributes:
        row: The Adw.ActionRow to add to the tab's group.
        path: The chosen output folder, or None to save next to each media file.
    """

    def __init__(self, get_parent, show_toast, on_changed):
        self._get_parent = get_parent
        self._show_toast = show_toast
        self._on_changed = on_changed
        self.path: str | None = None

        self.row = Adw.ActionRow(title="Output folder")
        self.row.set_use_markup(False)  # Folder names may contain "&" or "<".
        self.row.add_prefix(make_icon_prefix("folder-symbolic"))
        self._reset_button = flat_icon_button("edit-undo-symbolic", _RESET_TOOLTIP, self._on_reset)
        self.row.add_suffix(self._reset_button)
        self.row.add_suffix(flat_text_button("Change", self._on_choose))
        self.reload()

    def reload(self) -> None:
        """Take the remembered folder, if it is still usable, else "next to the file"."""
        saved = app_settings.get(saved_settings.MEDIA_OUTPUT_DIR, "")
        self._reset_button.set_visible(bool(saved))
        self.path = None
        if saved:
            if os.path.isdir(saved) and os.access(saved, os.W_OK | os.X_OK):
                self.path = saved
            else:
                self._show_toast("The remembered output folder isn’t available — saving next to the file instead")
        self.row.set_subtitle(self.path or _NEXT_TO_FILE)

    def _on_choose(self, *_) -> None:
        initial = self.path if self.path and os.path.isdir(self.path) else None
        file_dialogs.choose_folder(self._get_parent(), "Choose output folder", initial, self._on_chosen)

    def _on_chosen(self, folder: str) -> None:
        self.path = folder
        self.row.set_subtitle(folder)
        app_settings.set(saved_settings.MEDIA_OUTPUT_DIR, folder)
        self._reset_button.set_visible(True)
        self._on_changed()

    def _on_reset(self, *_) -> None:
        app_settings.remove(saved_settings.MEDIA_OUTPUT_DIR)
        self.path = None
        self._reset_button.set_visible(False)
        self.row.set_subtitle(_NEXT_TO_FILE)
        self._show_toast("Saving next to each file again")
        self._on_changed()
