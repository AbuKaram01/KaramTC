# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/media_tab/tab.py — The Audio/Video tab: choose a recording, get its text.

Handles UI only; all transcription logic lives in core/media.
"""
from __future__ import annotations

import importlib
import os
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

import settings as app_settings
from core.media import (
    MEDIA_EXTENSIONS, MediaReadError, TranscriptionCancelledError, probe_media, run_media_transcription,
    speech_engine_installed,
)
from core.media.journal import TranscriptJournal
from ui import dialogs, file_dialogs, saved_settings
from ui.formatting import format_bytes, format_duration
from ui.media_tab import job_setup
from ui.media_tab.done_view import DonePage
from ui.media_tab.missing_engine import build_engine_missing_page
from ui.media_tab.options import MediaOptions
from ui.media_tab.output_folder import OutputFolder
from ui.media_tab.progress_view import MediaProgressCard
from ui.widgets import (
    add_file_drop_target, centered_row, make_icon_prefix, pill_button, scrolled_clamp, status_page,
)

_PAGE_MAIN, _PAGE_MISSING = "main", "missing"
_MODE_SELECT, _MODE_PROGRESS, _MODE_DONE = "select", "progress", "done"
_NO_FILE_TITLE = "\u2014"


class MediaTab(Adw.Bin):
    def __init__(self, on_running_changed=None, on_open_speech_settings=None):
        """
        :param on_running_changed:      called whenever a transcription starts or ends.
        :param on_open_speech_settings: opens the Speech Settings dialog.
        """
        super().__init__()
        self._on_running_changed = on_running_changed
        self._on_open_speech_settings = on_open_speech_settings

        self._media_path: str | None = None
        self._cancel_event = threading.Event()
        self._is_running = False
        self._journal = TranscriptJournal()

        self._pages = Gtk.Stack()
        self.set_child(self._pages)
        self._pages.add_named(build_engine_missing_page(self.refresh), _PAGE_MISSING)
        self._pages.add_named(self._build_main_page(), _PAGE_MAIN)
        self.refresh()

    # ── Public interface (used by the main window) ────────────────────

    def is_running(self) -> bool:
        return self._is_running

    def refresh(self) -> None:
        """Re-checks the speech engine and model — called after Speech Settings changes."""
        importlib.invalidate_caches()        # a package installed while the app runs is found too
        self._pages.set_visible_child_name(_PAGE_MAIN if speech_engine_installed() else _PAGE_MISSING)
        self._update_banners()

    # ── Layout ────────────────────────────────────────────────────────

    def _build_main_page(self) -> Adw.ToastOverlay:
        self._toast_overlay = Adw.ToastOverlay()
        scroll, clamp = scrolled_clamp(maximum_size=620, tightening_threshold=480)
        self._toast_overlay.set_child(scroll)
        self._outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._outer.set_margin_top(6)
        clamp.set_child(self._outer)
        add_file_drop_target(self._toast_overlay, self._on_drop)

        self._build_empty_state()
        self._build_file_group()
        self._build_start_controls()
        self._progress_card = MediaProgressCard(on_stop=self._on_stop)
        self._outer.append(self._progress_card)
        self._done_page = DonePage(
            on_new_file=self._on_new_file, on_copied=lambda: self._toast("Text copied to clipboard"),
            on_error=self._toast,
        )
        self._outer.append(self._done_page.widget)
        self._set_mode(_MODE_SELECT)
        return self._toast_overlay

    def _build_empty_state(self) -> None:
        self._intro = status_page(
            "audio-x-generic-symbolic", "Choose an audio or video file",
            "Drag a recording here or press the button below\n"
            "Speech is turned into text on this computer with Whisper",
        )
        self._outer.append(self._intro)
        self._choose_box = centered_row(
            pill_button("Open audio or video…", "document-open-symbolic", self._on_choose_media, suggested=True)
        )
        self._outer.append(self._choose_box)

    def _build_file_group(self) -> None:
        self._file_group = Adw.PreferencesGroup()
        self._outer.append(self._file_group)

        self._file_row = Adw.ActionRow()
        self._file_row.set_use_markup(False)       # file names may contain & or <
        self._file_row.set_title(_NO_FILE_TITLE)
        self._file_row.add_prefix(make_icon_prefix("audio-x-generic-symbolic"))
        change_button = Gtk.Button(label="Change")
        change_button.add_css_class("flat")
        change_button.set_valign(Gtk.Align.CENTER)
        change_button.connect("clicked", self._on_choose_media)
        self._file_row.add_suffix(change_button)
        self._file_group.add(self._file_row)

        self._output_folder = OutputFolder(self.get_root, self._toast, self._on_output_folder_changed)
        self._file_group.add(self._output_folder.row)
        self._options = MediaOptions()
        self._options.add_to(self._file_group)

    def _build_start_controls(self) -> None:
        self._model_banner = Adw.Banner(button_label="Set Up")
        self._model_banner.connect("button-clicked", self._on_open_settings_clicked)
        self._outer.append(self._model_banner)

        self._resume_banner = Adw.Banner(
            title="A previous transcription of this file was interrupted — Start continues it",
            button_label="Start over",
        )
        self._resume_banner.connect("button-clicked", self._on_start_over)
        self._outer.append(self._resume_banner)

        self._start_button = pill_button(
            "Start transcription", "media-playback-start-symbolic", self._on_start_clicked, suggested=True,
        )
        self._start_button.set_halign(Gtk.Align.CENTER)
        self._outer.append(self._start_button)

    def _set_mode(self, mode: str) -> None:
        has_file = bool(self._media_path)
        selecting = mode == _MODE_SELECT
        show_empty = selecting and not has_file
        self._intro.set_visible(show_empty)
        self._choose_box.set_visible(show_empty)
        self._file_group.set_visible(selecting and has_file)
        self._start_button.set_visible(selecting and has_file)
        self._progress_card.set_visible(mode == _MODE_PROGRESS)
        self._done_page.set_visible(mode == _MODE_DONE)
        self._update_banners()

    def _update_banners(self) -> None:
        selecting = self._file_group.get_visible()
        status = saved_settings.speech_model_status()
        self._model_banner.set_title(status.message)
        self._model_banner.set_revealed(selecting and not status.ready)
        self._resume_banner.set_revealed(selecting and self._has_saved_progress())

    def _has_saved_progress(self) -> bool:
        return bool(
            self._media_path and saved_settings.speech_resume_enabled()
            and self._journal.has_saved(self._media_path)
        )

    def _toast(self, message: str) -> None:
        dialogs.show_toast(self._toast_overlay, message)

    def _set_running(self, running: bool) -> None:
        self._is_running = running
        if self._on_running_changed:
            self._on_running_changed()

    # ── Choosing the file ─────────────────────────────────────────────

    def _on_drop(self, _target, value, _x, _y) -> bool:
        if self._is_running:
            self._toast("A transcription is already running \u2014 stop it first")
            return False
        if isinstance(value, Gio.File):
            path = value.get_path()
            if path and os.path.splitext(path)[1].lower() in MEDIA_EXTENSIONS:
                self._set_media(path)
                return True
        self._toast("Unsupported file — use an audio or video file")
        return False

    def _on_choose_media(self, *_) -> None:
        if self._is_running:
            self._toast("A transcription is already running \u2014 stop it first")
            return
        media_filter = file_dialogs.make_filter(
            "Audio and video", mime_types=["audio/*", "video/*"], suffixes=sorted(MEDIA_EXTENSIONS),
        )
        all_filter = file_dialogs.make_filter("All files", patterns=["*"])
        file_dialogs.open_file(
            self.get_root(), "Open audio or video file", [media_filter, all_filter], self._set_media,
            on_not_local=lambda: self._toast("Please choose a file stored on this computer"),
        )

    def _set_media(self, path: str) -> None:
        try:
            info = probe_media(path)
        except MediaReadError as exc:
            self._toast(str(exc))
            return
        if info is not None and not info.has_audio:
            self._toast("This file has no audio track to transcribe")
            return
        self._media_path = path
        self._file_row.set_title(os.path.basename(path))
        self._file_row.set_subtitle(self._describe_media(path, info))
        self._output_folder.reload()
        self._set_mode(_MODE_SELECT)

    @staticmethod
    def _describe_media(path: str, info) -> str:
        try:
            parts = [format_bytes(os.path.getsize(path))]
        except OSError:
            parts = []
        if info is not None and info.duration:
            parts.append(format_duration(info.duration))
        return "  \u2022  ".join(parts)

    def _on_new_file(self, *_) -> None:
        self._media_path = None
        self._file_row.set_title(_NO_FILE_TITLE)
        self._file_row.set_subtitle("")
        self._set_mode(_MODE_SELECT)
        self._on_choose_media()

    def _on_output_folder_changed(self) -> None:
        self._update_banners()

    # ── Settings and saved progress ───────────────────────────────────

    def _on_open_settings_clicked(self, *_) -> None:
        if self._on_open_speech_settings:
            self._on_open_speech_settings()

    def _on_start_over(self, *_) -> None:
        if self._media_path:
            self._journal.drop(self._media_path)
        self._update_banners()

    # ── Starting ──────────────────────────────────────────────────────

    def _on_start_clicked(self, *_) -> None:
        if not self._media_path:
            return
        status = saved_settings.speech_model_status()
        problem = job_setup.problem_blocking_start(status.ready, status.message)
        if problem:
            self._toast(problem)
            return
        request = job_setup.build_request(self._media_path, self._output_folder.path, self._options)
        if os.path.exists(request.output_path) and not request.settings.resume:
            self._confirm_replace(request)
            return
        self._start(request)

    def _confirm_replace(self, request) -> None:
        dialogs.confirm(
            self.get_root(), "Replace existing file?",
            f"This folder already contains:\n\u2022 {os.path.basename(request.output_path)}\n\n"
            "Starting will replace it. To keep it, cancel and choose another output folder, "
            "or move or rename the file first.",
            accept_id="replace", accept_label="Replace", on_accept=lambda: self._start(request),
        )

    def _start(self, request) -> None:
        folder = os.path.dirname(request.output_path)
        if not job_setup.output_folder_is_usable(folder):
            self._toast(f"Can\u2019t save to \u201c{folder}\u201d \u2014 choose another output folder")
            return
        app_settings.set(saved_settings.MEDIA_LANGUAGE, request.settings.language or "")
        self._cancel_event = threading.Event()
        self._set_running(True)
        self._progress_card.start(os.path.basename(request.media_path))
        self._set_mode(_MODE_PROGRESS)
        threading.Thread(target=self._worker, args=(request, self._cancel_event), daemon=True).start()

    def _worker(self, request, cancel_event: threading.Event) -> None:
        try:
            result = run_media_transcription(request, self._progress_cb, cancel_event)
            GLib.idle_add(self._on_done, result)
        except TranscriptionCancelledError:
            GLib.idle_add(self._on_cancelled)
        except Exception as exc:
            GLib.idle_add(self._on_error, str(exc))

    def _on_stop(self, *_) -> None:
        self._cancel_event.set()
        self._progress_card.show_stopping()

    # ── Progress and completion (called on the main thread) ───────────

    def _progress_cb(self, kind: str, *args) -> None:
        GLib.idle_add(self._on_progress_event, kind, *args)

    def _on_progress_event(self, kind: str, *args) -> bool:
        self._progress_card.update(kind, *args)
        return GLib.SOURCE_REMOVE

    def _on_done(self, result) -> bool:
        self._set_running(False)
        self._done_page.show_result(result)
        self._set_mode(_MODE_DONE)
        self._toast("Transcription saved ✓")
        return GLib.SOURCE_REMOVE

    def _on_cancelled(self) -> bool:
        self._set_running(False)
        self._set_mode(_MODE_SELECT)
        if saved_settings.speech_resume_enabled():
            self._toast("Stopped — progress saved, Start continues from here")
        else:
            self._toast("Stopped")
        return GLib.SOURCE_REMOVE

    def _on_error(self, message: str) -> bool:
        self._set_running(False)
        self._set_mode(_MODE_SELECT)
        dialogs.show_message_dialog(self.get_root(), "Transcription error", message)
        return GLib.SOURCE_REMOVE
