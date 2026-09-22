# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/speech_settings/dialog.py — The "Speech Settings" dialog of the Audio/Video tab.

Opened from the main menu and from the tab's "Set Up" banner. Everything is
saved through settings.py as soon as it changes.
"""
from __future__ import annotations

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw

import settings as app_settings
from core.media import DEVICE_AUTO, DEVICE_CPU, DEVICE_GPU, DEVICES
from ui import saved_settings
from ui.speech_settings.model_group import ModelGroup
from ui.widgets import string_list, switch_row

_DEVICE_LABELS = {DEVICE_AUTO: "Automatic", DEVICE_CPU: "CPU", DEVICE_GPU: "GPU (NVIDIA CUDA)"}
_DEVICE_HINTS = {
    DEVICE_AUTO: "Uses the GPU when one is available, otherwise the CPU",
    DEVICE_CPU: "Works everywhere; slower for long recordings",
    DEVICE_GPU: "Much faster, but needs an NVIDIA GPU with its CUDA libraries",
}

# The one Speech Settings dialog that is currently open, if any.
_open_dialog: SpeechSettingsDialog | None = None


def present_speech_settings(parent, on_changed=None) -> None:
    """Opens Speech Settings over *parent*, unless it is already open."""
    global _open_dialog
    if _open_dialog is not None:
        return

    def forget(_dialog):
        global _open_dialog
        _open_dialog = None

    dialog = SpeechSettingsDialog(on_changed=on_changed)
    dialog.connect("closed", forget)
    _open_dialog = dialog
    dialog.present(parent)


class SpeechSettingsDialog(Adw.PreferencesDialog):
    def __init__(self, on_changed=None):
        """:param on_changed: called (no arguments) whenever the model setup changes."""
        super().__init__(title="Speech Settings")
        self.set_search_enabled(False)
        self.set_content_width(560)
        self.set_content_height(640)
        self._on_changed = on_changed or (lambda: None)

        page = Adw.PreferencesPage()
        self.add(page)
        self._model = ModelGroup(self._toast, self.get_root, self._on_changed)
        page.add(self._model.group)
        page.add(self._build_performance_group())
        page.add(self._build_progress_group())
        self.connect("closed", lambda *_: self._model.cancel_download())

    def _toast(self, message: str, timeout: int | None) -> None:
        toast = Adw.Toast(title=message)
        toast.set_use_markup(False)
        if timeout:
            toast.set_timeout(timeout)
        self.add_toast(toast)

    # ── Performance ───────────────────────────────────────────────────

    def _build_performance_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Performance")
        self._device_row = Adw.ComboRow()
        self._device_row.set_title("Processing device")
        self._device_row.set_model(string_list(_DEVICE_LABELS[device] for device in DEVICES))
        self._device_row.set_selected(DEVICES.index(saved_settings.speech_device()))
        self._device_row.connect("notify::selected", self._on_device_selected)
        group.add(self._device_row)
        self._update_device_subtitle()

        low, high = saved_settings.SPEECH_THREADS_RANGE
        threads = Adw.SpinRow.new_with_range(low, high, 1)
        threads.set_title("CPU threads")
        threads.set_subtitle("Used when running on the CPU. More is faster, but leaves less for other programs")
        threads.set_value(saved_settings.speech_threads())
        threads.connect(
            "notify::value", lambda row, _param: app_settings.set(saved_settings.SPEECH_THREADS, int(row.get_value())),
        )
        group.add(threads)
        return group

    def _on_device_selected(self, _row, _param) -> None:
        app_settings.set(saved_settings.SPEECH_DEVICE, DEVICES[self._device_row.get_selected()])
        self._update_device_subtitle()

    def _update_device_subtitle(self) -> None:
        self._device_row.set_subtitle(_DEVICE_HINTS[DEVICES[self._device_row.get_selected()]])

    # ── Saved progress ────────────────────────────────────────────────

    def _build_progress_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title="Interrupted transcriptions")
        row, _switch = switch_row(
            "Continue interrupted transcriptions",
            saved_settings.speech_resume_enabled(),
            lambda switch, _param: app_settings.set(saved_settings.SPEECH_RESUME, switch.get_active()),
            subtitle=(
                "After Stop or a crash, picks up where it left off instead of starting over. "
                "Off by default: the join point can occasionally cut or repeat a word"
            ),
        )
        group.add(row)
        return group
