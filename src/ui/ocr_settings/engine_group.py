# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/ocr_settings/engine_group.py — The "Recognition engine" group of OCR Settings.

Raw Tesseract tuning: engine mode, page segmentation, internal variables and
free-form custom parameters.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

import settings as app_settings
from providers.ocr_types import DEFAULT_OEM, DEFAULT_PSM, TESSERACT_TOGGLE_VARIABLES
from providers.tesseract import OEM_OPTIONS, PSM_OPTIONS, psm_index
from ui import saved_settings
from ui.widgets import string_list, switch_row

_EDGES_SCALE_RANGE = (1, 100)
_EDGES_SCALE_STEP = 1
_DEFAULT_OEM_INDEX = 3      # the "Default" entry of OEM_OPTIONS


class EngineGroup:
    def __init__(self, on_psm_changed):
        """:param on_psm_changed: called (no arguments) after a new page segmentation mode was saved."""
        self._on_psm_changed = on_psm_changed
        self.group = Adw.PreferencesGroup(
            title="Recognition engine",
            description="Advanced Tesseract tuning \u2014 the defaults work well for most pages",
        )
        self._build_oem_row()
        self._build_psm_row()
        self.group.add(self._build_tesseract_options())
        self._build_custom_parameters()

    def selected_psm(self) -> tuple[int, str] | None:
        """(mode number, short label) of the selected page segmentation mode."""
        index = self._psm_row.get_selected()
        if not 0 <= index < len(PSM_OPTIONS):
            return None
        value, label, _description = PSM_OPTIONS[index]
        return value, label

    # ── Engine mode and page segmentation ─────────────────────────────

    def _build_oem_row(self) -> None:
        self._oem_row = Adw.ComboRow()
        self._oem_row.set_title("Engine mode (OEM)")
        self._oem_row.set_model(string_list(label for _value, label, _description in OEM_OPTIONS))
        saved = app_settings.get(saved_settings.OCR_OEM, DEFAULT_OEM)
        self._oem_row.set_selected(
            next((i for i, (value, _l, _d) in enumerate(OEM_OPTIONS) if value == saved), _DEFAULT_OEM_INDEX)
        )
        self._oem_row.connect("notify::selected", self._on_oem_selected)
        self.group.add(self._oem_row)
        self._update_subtitle(self._oem_row, OEM_OPTIONS)

    def _build_psm_row(self) -> None:
        self._psm_row = Adw.ComboRow()
        self._psm_row.set_title("Page segmentation (PSM)")
        self._psm_row.set_model(string_list(label for _value, label, _description in PSM_OPTIONS))
        # psm_index() maps removed/unknown values (e.g. PSM 0 or 2 saved by an
        # earlier version) to the default mode instead of a wrong list position.
        self._psm_row.set_selected(psm_index(app_settings.get(saved_settings.OCR_PSM, DEFAULT_PSM)))
        self._psm_row.connect("notify::selected", self._on_psm_selected)
        self.group.add(self._psm_row)
        self._update_subtitle(self._psm_row, PSM_OPTIONS)

    @staticmethod
    def _update_subtitle(row: Adw.ComboRow, options) -> None:
        index = row.get_selected()
        if 0 <= index < len(options):
            row.set_subtitle(options[index][2])

    def _on_oem_selected(self, row, _param) -> None:
        app_settings.set(saved_settings.OCR_OEM, OEM_OPTIONS[row.get_selected()][0])
        self._update_subtitle(row, OEM_OPTIONS)

    def _on_psm_selected(self, row, _param) -> None:
        app_settings.set(saved_settings.OCR_PSM, PSM_OPTIONS[row.get_selected()][0])
        self._update_subtitle(row, PSM_OPTIONS)
        self._on_psm_changed()

    # ── Tesseract Options (internal variables) ────────────────────────

    def _build_tesseract_options(self) -> Adw.ExpanderRow:
        expander = Adw.ExpanderRow()
        expander.set_title("Tesseract Options")
        expander.set_subtitle(
            "Advanced, internal Tesseract tuning variables \u2014 leave off unless "
            "you know what a specific one does"
        )
        expander.add_row(self._setting_switch_row(saved_settings.OCR_PRESERVE_SPACES, "preserve_interword_spaces"))
        for variable in TESSERACT_TOGGLE_VARIABLES:
            expander.add_row(self._setting_switch_row(saved_settings.toggle_setting_key(variable), variable))
        self._add_edges_rows(expander)
        return expander

    @staticmethod
    def _setting_switch_row(setting_key: str, title: str) -> Adw.ActionRow:
        """One switch bound to a boolean setting. Titles are the raw variable
        names (not friendly prose): that is exactly what a user tuning these
        already looks for, and guessing a description for an internal knob
        risks being subtly wrong."""
        row, _switch = switch_row(
            title, bool(app_settings.get(setting_key, False)),
            lambda switch, _param: app_settings.set(setting_key, switch.get_active()),
        )
        return row

    def _add_edges_rows(self, expander: Adw.ExpanderRow) -> None:
        edges_row, edges_switch = switch_row(
            "edges_max_children_per_outline",
            bool(app_settings.get(saved_settings.OCR_EDGES_ENABLED, False)),
        )
        expander.add_row(edges_row)

        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, *_EDGES_SCALE_RANGE, _EDGES_SCALE_STEP)
        scale.set_value(app_settings.get(saved_settings.OCR_EDGES_VALUE, saved_settings.EDGES_DEFAULT_VALUE))
        scale.set_draw_value(True)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_hexpand(True)
        scale.set_sensitive(edges_switch.get_active())
        scale.connect(
            "value-changed",
            lambda widget: app_settings.set(saved_settings.OCR_EDGES_VALUE, int(widget.get_value())),
        )
        edges_switch.connect("notify::active", lambda switch, _param: self._on_edges_toggled(switch, scale))
        scale.set_margin_start(12)
        scale.set_margin_end(12)
        scale.set_margin_top(4)
        scale.set_margin_bottom(8)
        expander.add_row(scale)

    @staticmethod
    def _on_edges_toggled(switch: Gtk.Switch, scale: Gtk.Scale) -> None:
        enabled = switch.get_active()
        app_settings.set(saved_settings.OCR_EDGES_ENABLED, enabled)
        scale.set_sensitive(enabled)

    # ── Custom parameters ─────────────────────────────────────────────

    def _build_custom_parameters(self) -> None:
        entry = Adw.EntryRow()
        entry.set_title("Custom parameters")
        entry.set_text(app_settings.get(saved_settings.OCR_CUSTOM_PARAMS, ""))
        entry.connect("changed", lambda row: app_settings.set(saved_settings.OCR_CUSTOM_PARAMS, row.get_text()))
        self.group.add(entry)

        hint = Adw.ActionRow()
        hint.set_title("Format")
        hint.set_subtitle(
            "key=value pairs, separated by semicolons \u2014 "
            "e.g. tessedit_char_whitelist=0123456789; user_defined_dpi=300"
        )
        hint.set_subtitle_lines(0)
        hint.add_css_class("dim-label")
        self.group.add(hint)
