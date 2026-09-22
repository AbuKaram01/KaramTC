# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/media_tab/progress_view.py — The progress card shown while a recording is transcribed.
"""
from __future__ import annotations

import time

from core.media import events, format_clock, language_name
from ui.formatting import format_remaining
from ui.progress_frame import ProgressFrame

_MIN_SECONDS_FOR_ETA = 8            # an estimate from the first few seconds would only jump around
_MAX_PREVIEW_CHARS = 90


class MediaProgressCard(ProgressFrame):
    """Renders the pipeline's progress events (see core/media/events.py)."""

    def __init__(self, on_stop):
        super().__init__(on_stop)
        self._language_text = ""
        self._started_at: float | None = None
        self._first_position = 0.0
        self._handlers = {
            events.STAGE: self._on_stage,
            events.LANGUAGE: self._on_language,
            events.PROGRESS: self._on_progress,
            events.NOTE: self._on_note,
        }

    def start(self, media_name: str) -> None:
        self._language_text = ""
        self._started_at = None
        self.reset(f"Preparing — {media_name}")

    def update(self, kind: str, *args) -> None:
        handler = self._handlers.get(kind)
        if handler:
            handler(*args)

    # ── Event handlers ────────────────────────────────────────────────

    def _on_stage(self, label):
        self._title.set_text(label)

    def _on_language(self, code, probability):
        text = language_name(code)
        if probability is not None:
            text += f" detected ({probability * 100:.0f}% sure)"
        self._language_text = text
        self._detail.set_text(text)

    def _on_note(self, message):
        self._detail.set_text(message)

    def _on_progress(self, position, duration, text):
        if self._started_at is None:
            self._started_at = time.monotonic()
            self._first_position = position
        fraction = position / duration if duration else 0.0
        self._set_progress(fraction, f"{format_clock(position)} / {format_clock(duration)}  •  {fraction * 100:.0f}%")
        self._detail.set_text(self._detail_text(position, duration, text))

    # ── Detail line ───────────────────────────────────────────────────

    def _detail_text(self, position: float, duration: float, text: str) -> str:
        parts = [self._language_text] if self._language_text else []
        parts.append(self._speed_and_eta(position, duration))
        preview = text if len(text) <= _MAX_PREVIEW_CHARS else text[: _MAX_PREVIEW_CHARS - 1] + "…"
        return "  •  ".join(part for part in parts if part) + (f"\n{preview}" if preview else "")

    def _speed_and_eta(self, position: float, duration: float) -> str:
        elapsed = time.monotonic() - (self._started_at or time.monotonic())
        done = position - self._first_position
        if elapsed < _MIN_SECONDS_FOR_ETA or done <= 0:
            return ""
        speed = done / elapsed
        return f"{speed:.1f}× real time, {format_remaining((duration - position) / speed)} left"
