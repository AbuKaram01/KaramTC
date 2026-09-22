# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/speech_settings/model_group.py — Which speech model to use, and getting it.
"""
from __future__ import annotations

import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

import settings as app_settings
from core.media import SOURCE_CUSTOM, SOURCE_MANAGED, DownloadCancelledError, model_store
from core.media.model_location import model_status
from ui import file_dialogs, saved_settings
from ui.formatting import format_bytes
from ui.widgets import flat_icon_button, flat_text_button, make_icon_prefix, string_list

# One entry per downloadable model, then the user's own folder: (label, source, model id).
# The recommended model says so right in its label.
_CHOICES = [
    (f"Download {model.display_label}", SOURCE_MANAGED, model.id) for model in model_store.MODELS
] + [("Use a model folder I already have", SOURCE_CUSTOM, None)]
_CUSTOM_DESCRIPTION = "Use a faster-whisper (CTranslate2) model folder you already have. Nothing is downloaded."
_ERROR_TOAST_TIMEOUT_S = 5


class ModelGroup:
    def __init__(self, show_toast, get_parent, on_changed):
        """
        :param show_toast:  shows a short message over the dialog.
        :param get_parent:  returns the window a folder chooser should open over.
        :param on_changed:  called whenever the model setup changes (so the tab can refresh).
        """
        self._show_toast = show_toast
        self._get_parent = get_parent
        self._on_changed = on_changed
        self._cancel_event: threading.Event | None = None      # set while a download runs
        self._downloading = False
        self._downloading_model = model_store.get_model()      # which model the running download is for

        self.group = Adw.PreferencesGroup(title="Speech model")
        self._build_source_row()
        self._build_managed_row()
        self._build_custom_row()
        self._refresh()

    # ── Construction ──────────────────────────────────────────────────

    def _build_source_row(self) -> None:
        self._source_row = Adw.ComboRow()
        self._source_row.set_title("Model")
        self._source_row.add_prefix(make_icon_prefix("audio-input-microphone-symbolic"))
        self._source_row.set_model(string_list([label for label, _source, _model_id in _CHOICES]))
        self._source_row.set_selected(self._saved_choice_index())
        self._source_row.connect("notify::selected", self._on_choice_selected)
        self.group.add(self._source_row)

    def _build_managed_row(self) -> None:
        self._managed_row = Adw.ActionRow(title=model_store.get_model().display_label)   # set properly by _refresh
        self._managed_row.set_use_markup(False)     # shows server error messages
        self._managed_row.add_prefix(make_icon_prefix("folder-download-symbolic"))
        self._suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._suffix.set_valign(Gtk.Align.CENTER)
        self._download_button = flat_icon_button("folder-download-symbolic", "Download", self._on_download)
        self._cancel_button = flat_text_button("Pause", self._on_cancel)
        self._delete_button = flat_icon_button("user-trash-symbolic", "Delete the downloaded model", self._on_delete)
        for widget in (self._download_button, self._cancel_button, self._delete_button):
            self._suffix.append(widget)
        self._managed_row.add_suffix(self._suffix)
        self.group.add(self._managed_row)

    def _build_custom_row(self) -> None:
        self._custom_row = Adw.ActionRow(title="Model folder")
        self._custom_row.set_use_markup(False)      # shows a folder path
        self._custom_row.add_prefix(make_icon_prefix("folder-symbolic"))
        self._custom_row.add_suffix(flat_text_button("Choose…", self._on_choose_folder))
        self.group.add(self._custom_row)

    # ── Showing the state ─────────────────────────────────────────────

    @staticmethod
    def _saved_choice_index() -> int:
        """The entry of _CHOICES that matches the saved settings."""
        if saved_settings.speech_model_source() == SOURCE_CUSTOM:
            return len(_CHOICES) - 1
        saved_id = saved_settings.speech_model_id()
        return next(index for index, (_label, _source, model_id) in enumerate(_CHOICES) if model_id == saved_id)

    def _selected_source(self) -> str:
        return _CHOICES[self._source_row.get_selected()][1]

    def _selected_model(self) -> model_store.WhisperModel:
        """The downloadable model currently chosen (when the custom folder is chosen: the last one chosen)."""
        return model_store.get_model(_CHOICES[self._source_row.get_selected()][2] or saved_settings.speech_model_id())

    def _custom_dir(self) -> str:
        return app_settings.get(saved_settings.SPEECH_MODEL_DIR, "")

    def _refresh(self) -> None:
        managed = self._selected_source() == SOURCE_MANAGED
        model = self._selected_model()
        self._managed_row.set_visible(managed)
        self._custom_row.set_visible(not managed)
        status = model_status(self._selected_source(), self._custom_dir(), model.id)
        if managed:
            self._managed_row.set_title(model.display_label)
            self.group.set_description(
                f"{model.label} {model.summary} It is downloaded once ({model.size_text}) and then works offline."
            )
            self._show_managed_state(status.message, status.ready)
        else:
            self.group.set_description(_CUSTOM_DESCRIPTION)
            self._custom_row.set_subtitle(self._custom_dir() or "No folder chosen")
            if not status.ready and self._custom_dir():
                self._custom_row.set_subtitle(f"{self._custom_dir()}\n{status.message}")

    def _show_managed_state(self, message: str, ready: bool) -> None:
        if not self._downloading:
            self._managed_row.set_subtitle(message)
        self._download_button.set_visible(not ready and not self._downloading)
        self._cancel_button.set_visible(self._downloading)
        self._cancel_button.set_sensitive(True)
        self._delete_button.set_visible(ready and not self._downloading)
        self._source_row.set_sensitive(not self._downloading)

    # ── Source and folder ─────────────────────────────────────────────

    def _on_choice_selected(self, _row, _param) -> None:
        _label, source, model_id = _CHOICES[self._source_row.get_selected()]
        app_settings.set(saved_settings.SPEECH_MODEL_SOURCE, source)
        if model_id:        # picking the folder option keeps the last downloadable model remembered
            app_settings.set(saved_settings.SPEECH_MODEL_CHOICE, model_id)
        self._refresh()
        self._on_changed()

    def _on_choose_folder(self, *_) -> None:
        current = self._custom_dir()
        initial = current if current and os.path.isdir(current) else None
        file_dialogs.choose_folder(self._get_parent(), "Choose the model folder", initial, self._on_folder_chosen)

    def _on_folder_chosen(self, folder: str) -> None:
        app_settings.set(saved_settings.SPEECH_MODEL_DIR, folder)
        self._refresh()
        self._on_changed()

    # ── Downloading ───────────────────────────────────────────────────

    def cancel_download(self) -> None:
        """Stops a running download (what was fetched is kept, so it can continue later)."""
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _on_download(self, *_) -> None:
        if self._downloading:
            return
        self._downloading = True
        self._downloading_model = self._selected_model()
        self._cancel_event = threading.Event()
        self._managed_row.set_subtitle("Starting the download…")
        self._refresh()
        threading.Thread(
            target=self._download_worker, args=(self._cancel_event, self._downloading_model.id), daemon=True,
        ).start()

    def _on_cancel(self, *_) -> None:
        self.cancel_download()
        self._cancel_button.set_sensitive(False)

    def _download_worker(self, cancel_event: threading.Event, model_id: str) -> None:
        try:
            model_store.download(
                lambda done, total, what: GLib.idle_add(self._on_progress, done, total, what), cancel_event,
                model_id=model_id,
            )
            GLib.idle_add(self._on_download_finished, None, False)
        except DownloadCancelledError:
            GLib.idle_add(self._on_download_finished, None, True)
        except Exception as exc:
            GLib.idle_add(self._on_download_finished, str(exc), False)

    def _on_progress(self, done: int, total: int, what: str) -> bool:
        if self._downloading and total:
            self._managed_row.set_subtitle(
                f"{what} — {done * 100 // total}%  ({format_bytes(done)} of {format_bytes(total)})"
            )
        return GLib.SOURCE_REMOVE

    def _on_download_finished(self, error: str | None, paused: bool) -> bool:
        self._downloading = False
        self._cancel_event = None
        self._refresh()
        if error:
            self._managed_row.set_subtitle(error)
            self._show_toast(f"Download failed: {error}", _ERROR_TOAST_TIMEOUT_S)
        elif paused:
            self._show_toast("Paused — Download continues where it stopped", None)
        else:
            self._show_toast(f"{self._downloading_model.label} is ready ✓", None)
        self._on_changed()
        return GLib.SOURCE_REMOVE

    def _on_delete(self, *_) -> None:
        model_store.delete(model_id=self._selected_model().id)
        self._refresh()
        self._show_toast("The downloaded model was removed", None)
        self._on_changed()
