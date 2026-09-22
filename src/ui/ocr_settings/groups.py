# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/ocr_settings/groups.py — Language source, performance and page-image groups of OCR Settings.

Every control saves its value as soon as it changes.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

import settings as app_settings
from config import (
    BOOK_IMAGE_DPI, BOOK_IMAGE_DPI_RANGE, BOOK_IMAGE_JPEG_QUALITY, BOOK_IMAGE_JPEG_QUALITY_RANGE,
)
from core.book import normalize_image_dpi, normalize_jpeg_quality
from providers import tessdata_manager
from providers.engine_settings import SYSTEM_LANG_SOURCE
from providers.tesseract import (
    CPU_USAGE_OPTIONS, DEFAULT_CPU_USAGE, cpu_cores, normalize_cpu_usage, threads_for_usage,
)
from ui import saved_settings
from ui.widgets import flat_text_button, make_icon_prefix, string_list

SOURCE_IDS = [SYSTEM_LANG_SOURCE] + [tier for tier, _label in tessdata_manager.QUALITY_TIERS]
_SYSTEM_SOURCE_DESCRIPTION = "Uses tesseract-ocr-<lang> packages already installed via apt / dnf / pacman / brew"
_CPU_USAGE_IDS = [value for value, _label in CPU_USAGE_OPTIONS]


class LanguageSourceGroup:
    """Where Tesseract loads language files from, and the way into the download manager."""

    def __init__(self, on_source_changed, on_manage):
        """
        :param on_source_changed: called with the new source id after it was saved.
        :param on_manage:         called (no arguments) to open the language manager.
        """
        self._on_source_changed = on_source_changed
        self.group = Adw.PreferencesGroup(
            title="Language data", description="Where Tesseract loads language files from",
        )
        self._descriptions = [_SYSTEM_SOURCE_DESCRIPTION]
        self._descriptions += [label for _tier, label in tessdata_manager.QUALITY_TIERS]

        self._combo = Adw.ComboRow()
        self._combo.set_title("Language source")
        self._combo.add_prefix(make_icon_prefix("preferences-desktop-locale-symbolic"))
        self._combo.set_model(string_list(
            ["System"] + [tier.capitalize() for tier, _label in tessdata_manager.QUALITY_TIERS]
        ))
        saved = saved_settings.valid_lang_source()
        self._combo.set_selected(SOURCE_IDS.index(saved) if saved in SOURCE_IDS else 0)
        self._combo.connect("notify::selected", self._on_selected)
        self.group.add(self._combo)
        self._update_source_subtitle()

        self._manage_row = Adw.ActionRow()
        self._manage_row.set_title("Manage downloaded languages")
        self._manage_row.add_prefix(make_icon_prefix("folder-download-symbolic"))
        manage_button = flat_text_button("Open", lambda *_: on_manage())
        self._manage_row.add_suffix(manage_button)
        self._manage_row.set_activatable_widget(manage_button)
        self.group.add(self._manage_row)
        self._update_manage_row()

    @property
    def selected_source(self) -> str:
        return SOURCE_IDS[self._combo.get_selected()]

    def _on_selected(self, _row, _param) -> None:
        app_settings.set(saved_settings.OCR_LANG_SOURCE, self.selected_source)
        self._update_source_subtitle()
        self._update_manage_row()
        self._on_source_changed(self.selected_source)

    def _update_source_subtitle(self) -> None:
        index = self._combo.get_selected()
        if 0 <= index < len(self._descriptions):
            self._combo.set_subtitle(self._descriptions[index])

    def _update_manage_row(self) -> None:
        is_system = self.selected_source == SYSTEM_LANG_SOURCE
        self._manage_row.set_sensitive(not is_system)
        self._manage_row.set_subtitle(
            "Choose a downloaded source above to manage its languages"
            if is_system else
            "Download or remove language packs for the selected quality tier"
        )


def describe_cpu_usage(usage: str, cores: int) -> str:
    """The explanation shown under the CPU usage choice, for this machine."""
    threads = threads_for_usage(usage, cores)
    plural = "core" if cores == 1 else "cores"
    if usage == "low":
        return "1 core. Keeps your computer responsive for other work, and is often just as fast"
    if usage == "balanced":
        return f"{threads} of your {cores} {plural}"
    if usage == "max":
        return f"All {cores} {plural}. Best when you aren\u2019t using the computer for anything else"
    if threads is None:
        return f"Recommended. The engine\u2019s own default, which suits your {cores} {plural}"
    return f"Recommended. Matches your {cores} {plural} \u2014 extra threads would only slow OCR down"


class PerformanceGroup:
    def __init__(self):
        self.group = Adw.PreferencesGroup(
            title="Performance",
            description=(
                "How much of your processor OCR may use. A long book can take hours, and a "
                "lower setting keeps the computer usable meanwhile. Applies the next time an "
                "extraction starts or is resumed."
            ),
        )
        self._row = Adw.ComboRow()
        self._row.set_title("CPU usage")
        self._row.set_model(string_list(label for _value, label in CPU_USAGE_OPTIONS))
        saved = normalize_cpu_usage(app_settings.get(saved_settings.OCR_CPU_USAGE, DEFAULT_CPU_USAGE))
        self._row.set_selected(_CPU_USAGE_IDS.index(saved))
        self._refresh_subtitle()
        self._row.connect("notify::selected", self._on_selected)
        self.group.add(self._row)

    def _selected_usage(self) -> str:
        index = self._row.get_selected()
        return _CPU_USAGE_IDS[index] if 0 <= index < len(_CPU_USAGE_IDS) else DEFAULT_CPU_USAGE

    def _refresh_subtitle(self) -> None:
        self._row.set_subtitle(describe_cpu_usage(self._selected_usage(), cpu_cores()))

    def _on_selected(self, _row, _param) -> None:
        self._refresh_subtitle()
        app_settings.set(saved_settings.OCR_CPU_USAGE, self._selected_usage())


class PageImagesGroup:
    """How scanned PDF pages are rendered to images before OCR."""

    def __init__(self):
        self.group = Adw.PreferencesGroup(
            title="PDF page images",
            description=(
                "How scanned PDF pages are converted to images before OCR (PDF tab). "
                "Also sets the image quality of scanned pages in a searchable PDF. "
                "Higher values read small or faint text better, but are slower and "
                "use more disk space."
            ),
        )
        self.group.add(self._spin_row(
            "Resolution (DPI)", BOOK_IMAGE_DPI_RANGE, step=50,
            subtitle=(f"Default {BOOK_IMAGE_DPI}. Try 300 for small print or faint scans; "
                      "150 is faster for clean, large type"),
            key=saved_settings.PDF_IMAGE_DPI, default=BOOK_IMAGE_DPI, normalize=normalize_image_dpi,
        ))
        self.group.add(self._spin_row(
            "JPEG quality", BOOK_IMAGE_JPEG_QUALITY_RANGE, step=5,
            subtitle=(f"Default {BOOK_IMAGE_JPEG_QUALITY}. Lower makes smaller files; "
                      "very low values can blur text and hurt accuracy"),
            key=saved_settings.PDF_JPEG_QUALITY, default=BOOK_IMAGE_JPEG_QUALITY, normalize=normalize_jpeg_quality,
        ))

    @staticmethod
    def _spin_row(title, value_range, *, step, subtitle, key, default, normalize) -> Adw.SpinRow:
        row = Adw.SpinRow.new_with_range(*value_range, step)
        row.set_title(title)
        row.set_subtitle(subtitle)
        row.set_snap_to_ticks(True)
        row.set_value(normalize(app_settings.get(key, default)))
        row.connect("notify::value", lambda spin, _param: app_settings.set(key, normalize(spin.get_value())))
        return row
