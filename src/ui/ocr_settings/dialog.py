# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/ocr_settings/dialog.py — The shared "OCR Settings" dialog.

Opened from the main menu, Ctrl+, and a gear button on each tab. Everything
is persisted through settings.py, so both tabs always read the same engine
configuration — there is one OCR engine, not a per-tab one.
"""
from __future__ import annotations

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw

from providers.engine_settings import SYSTEM_LANG_SOURCE
from ui.ocr_settings.engine_group import EngineGroup
from ui.ocr_settings.groups import LanguageSourceGroup, PageImagesGroup, PerformanceGroup
from ui.ocr_settings.language_manager import LanguageManagerDialog
from ui.ocr_settings.osd_offer import OsdOffer

# The one OCR Settings dialog that is currently open, if any.
_open_dialog: OcrSettingsDialog | None = None


def present_ocr_settings(parent, on_changed=None) -> None:
    """
    Opens the shared OCR Settings dialog over *parent*, unless one is already
    open. Every entry point goes through here, so a keyboard shortcut pressed
    while the dialog is showing can't stack a second copy on top of it.
    """
    global _open_dialog
    if _open_dialog is not None:
        return

    def forget(_dialog):
        global _open_dialog
        _open_dialog = None

    dialog = OcrSettingsDialog(on_changed=on_changed)
    dialog.connect("closed", forget)
    _open_dialog = dialog
    dialog.present(parent)


class OcrSettingsDialog(Adw.PreferencesDialog):
    """Language source, performance, page images and the recognition engine."""

    def __init__(self, on_changed=None):
        """
        :param on_changed: called (no arguments) whenever a change here could
            affect which languages are available to select — the language
            source changed, or a language was downloaded/deleted in the
            manager. The opening tab uses it to refresh its language combo.
        """
        super().__init__(title="OCR Settings")
        self.set_search_enabled(False)
        # A bit wider/taller than the libadwaita default: this dialog grew a lot
        # once the Tesseract Options group was added, and the page still scrolls
        # internally for anything beyond this.
        self.set_content_width(560)
        self.set_content_height(720)
        self._on_changed = on_changed
        self._osd_offer = OsdOffer(self)

        page = Adw.PreferencesPage()
        self.add(page)
        self._language_source = LanguageSourceGroup(self._on_source_changed, self._open_language_manager)
        self._engine = EngineGroup(on_psm_changed=self._offer_osd_if_needed)
        for group in (
            self._language_source.group, PerformanceGroup().group, PageImagesGroup().group, self._engine.group,
        ):
            page.add(group)

    def _on_source_changed(self, _source: str) -> None:
        if self._on_changed:
            self._on_changed()
        self._offer_osd_if_needed()

    def _offer_osd_if_needed(self) -> None:
        selected = self._engine.selected_psm()
        if selected is not None:
            psm, label = selected
            self._osd_offer.offer_if_needed(psm, label, self._language_source.selected_source)

    def _open_language_manager(self) -> None:
        source = self._language_source.selected_source
        if source == SYSTEM_LANG_SOURCE:
            return
        LanguageManagerDialog(source, on_changed=self._on_changed).present(self)
