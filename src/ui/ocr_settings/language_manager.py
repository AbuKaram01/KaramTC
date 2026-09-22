# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/ocr_settings/language_manager.py — Download / delete language packs for one quality tier.
"""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

import settings as app_settings
from providers import tessdata_manager
from providers.ocr_types import DEFAULT_PSM
from providers.tesseract import LANG_NAMES, psm_needs_osd
from ui import saved_settings
from ui.widgets import clear_children, flat_icon_button

# Downloadable support files that are not OCR languages, so they aren't in
# LANG_NAMES but still need a readable name in rows and toasts.
_SUPPORT_NAMES = {tessdata_manager.OSD_CODE: "Orientation and script detection"}
_LIST_MIN_HEIGHT = 420


def display_name(code: str) -> str:
    return LANG_NAMES.get(code) or _SUPPORT_NAMES.get(code, code)


class PackRow:
    """One downloadable item in the list: a language, or the osd file."""

    def __init__(self, code: str, on_download, on_delete):
        self.code = code
        self._on_download = on_download
        self._on_delete = on_delete
        self._progress_label: Gtk.Label | None = None

        self._action_row = Adw.ActionRow()
        self._action_row.set_title(display_name(code))
        self._action_row.set_subtitle(code)
        # One box added once as the suffix, whose *children* are swapped on
        # refresh — simpler and more robust than adding/removing widgets on
        # the ActionRow itself.
        self._suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._suffix.set_valign(Gtk.Align.CENTER)
        self._action_row.add_suffix(self._suffix)

        self.list_row = Gtk.ListBoxRow()
        self.list_row.set_child(self._action_row)
        self.list_row.set_activatable(False)

    def matches(self, query: str) -> bool:
        return query in f"{self._action_row.get_title()} {self._action_row.get_subtitle()}".lower()

    def refresh(self, quality: str, downloading: bool, another_download_active: bool) -> None:
        clear_children(self._suffix)
        self._progress_label = None
        if downloading:
            self._show_progress()
        elif tessdata_manager.is_downloaded(quality, self.code):
            self._show_delete_button()
        else:
            self._show_download_button(enabled=not another_download_active)

    def set_progress(self, percent) -> None:
        if self._progress_label is not None:
            self._progress_label.set_text(f"{percent}%" if percent is not None else "\u2026")

    def _show_progress(self) -> None:
        self._suffix.append(Gtk.Spinner(spinning=True))
        self._progress_label = Gtk.Label(label="\u2026")
        self._progress_label.add_css_class("dim-label")
        self._suffix.append(self._progress_label)

    def _show_delete_button(self) -> None:
        check = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check.add_css_class("success")
        self._suffix.append(check)
        self._suffix.append(flat_icon_button(
            "user-trash-symbolic", "Delete downloaded language", lambda *_: self._on_delete(self),
        ))

    def _show_download_button(self, enabled: bool) -> None:
        button = flat_icon_button("folder-download-symbolic", "Download", lambda *_: self._on_download(self))
        button.set_sensitive(enabled)
        self._suffix.append(button)


class LanguageManagerDialog(Adw.PreferencesDialog):
    """Download / delete individual language packs for one quality tier."""

    def __init__(self, quality: str, on_changed=None):
        super().__init__(title=f"Manage Languages \u2014 {quality.capitalize()}")
        self.set_search_enabled(False)
        self._quality = quality
        self._on_changed = on_changed
        self._active_download: str | None = None

        page = Adw.PreferencesPage()
        self.add(page)
        self._rows: dict[Gtk.ListBoxRow, PackRow] = {}
        self._add_orientation_group(page)
        self._add_search_group(page)
        self._add_language_list(page)

    # ── Construction ──────────────────────────────────────────────────

    def _new_row(self, code: str) -> PackRow:
        row = PackRow(code, self._on_download, self._on_delete)
        row.refresh(self._quality, downloading=False, another_download_active=False)
        self._rows[row.list_row] = row
        return row

    def _add_orientation_group(self, page: Adw.PreferencesPage) -> None:
        """osd.traineddata isn't a language, so it gets its own small group
        (outside the searchable list) with the same download/delete controls.
        Needed by the "+ OSD" page segmentation modes."""
        group = Adw.PreferencesGroup(
            title="Orientation detection",
            description="Used by the \u201cAuto + OSD\u201d and \u201cSparse text + OSD\u201d modes in OCR Settings",
        )
        page.add(group)
        listbox = self._new_listbox()
        osd_row = self._new_row(tessdata_manager.OSD_CODE)
        listbox.append(osd_row.list_row)
        group.add(listbox)

    def _add_search_group(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup()
        page.add(group)
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search languages\u2026")
        self._search_entry.connect("search-changed", lambda *_: self._listbox.invalidate_filter())
        group.add(self._search_entry)

    def _add_language_list(self, page: Adw.PreferencesPage) -> None:
        group = Adw.PreferencesGroup()
        page.add(group)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(_LIST_MIN_HEIGHT)
        scroll.set_vexpand(True)

        self._listbox = self._new_listbox()
        self._listbox.set_filter_func(self._matches_search)
        scroll.set_child(self._listbox)
        group.add(scroll)

        for code, _name in sorted(LANG_NAMES.items(), key=lambda item: item[1]):
            self._listbox.append(self._new_row(code).list_row)

    @staticmethod
    def _new_listbox() -> Gtk.ListBox:
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        return listbox

    def _matches_search(self, list_row: Gtk.ListBoxRow) -> bool:
        query = self._search_entry.get_text().strip().lower()
        row = self._rows.get(list_row)
        return not query or row is None or row.matches(query)

    # ── Download / delete ─────────────────────────────────────────────

    def _refresh(self, row: PackRow) -> None:
        row.refresh(
            self._quality,
            downloading=self._active_download == row.code,
            another_download_active=self._active_download is not None,
        )

    def _on_download(self, row: PackRow) -> None:
        if self._active_download is not None:
            return
        self._active_download = row.code
        self._refresh(row)
        threading.Thread(target=self._download_worker, args=(row,), daemon=True).start()

    def _download_worker(self, row: PackRow) -> None:
        try:
            tessdata_manager.download(
                self._quality, row.code, progress_cb=lambda percent: GLib.idle_add(self._show_progress, row, percent),
            )
            GLib.idle_add(self._on_download_done, row, None)
        except Exception as exc:
            GLib.idle_add(self._on_download_done, row, str(exc))

    def _show_progress(self, row: PackRow, percent) -> bool:
        row.set_progress(percent)
        return GLib.SOURCE_REMOVE

    def _on_download_done(self, row: PackRow, error: str | None) -> bool:
        self._active_download = None
        self._refresh(row)
        if error:
            self._toast(f"Could not download {display_name(row.code)}: {error}")
        else:
            self._toast(f"{display_name(row.code)} downloaded \u2713")
            self._notify_changed(row.code)
        return GLib.SOURCE_REMOVE

    def _on_delete(self, row: PackRow) -> None:
        tessdata_manager.delete(self._quality, row.code)
        self._refresh(row)
        selected_psm = app_settings.get(saved_settings.OCR_PSM, DEFAULT_PSM)
        if row.code == tessdata_manager.OSD_CODE and psm_needs_osd(selected_psm):
            self._toast(
                "Orientation data removed \u2014 the selected page segmentation mode "
                "needs it, so re-download it or pick another mode"
            )
        else:
            self._toast(f"{display_name(row.code)} removed")
        self._notify_changed(row.code)

    def _notify_changed(self, code: str) -> None:
        """Language lists only need refreshing when an actual language changed."""
        if self._on_changed and code not in tessdata_manager.NON_LANGUAGE_CODES:
            self._on_changed()

    def _toast(self, message: str) -> None:
        root = self.get_root()
        show_toast = getattr(root, "show_toast", None) if root else None
        if show_toast is not None:
            show_toast(message)
