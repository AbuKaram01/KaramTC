# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/extraction.py — The audio/video → text pipeline.

  Check     — the file exists and the speech model is usable.
  Resume    — optionally pick up an interrupted transcription of the same file.
  Load      — load the speech model.
  Transcribe — stream segments, recording each one as it arrives.
  Save      — write the transcript atomically and forget the saved progress.

No GTK dependency — can be tested independently.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Callable

from core.media import events
from core.media.constants import SAMPLE_RATE
from core.media.engine import StreamInfo, WhisperEngine
from core.media.errors import NoSpeechError, TranscriptionCancelledError
from core.media.job import EngineSettings, MediaRequest, MediaResult
from core.media.journal import (
    JournalWriter, TranscriptJournal, model_signature, plan_resume,
)
from core.media.model_location import problems_with_model_dir
from core.media.output import write_atomically
from core.media.segments import Segment, plain_text, render, render_text

EngineFactory = Callable[[EngineSettings, Callable[[str], None]], WhisperEngine]

# Replaced in tests, and the one place that decides how the model is loaded.
default_engine_factory: EngineFactory = WhisperEngine.load


class MediaTranscription:
    """One run of the pipeline; use run_media_transcription() to execute it."""

    def __init__(
        self,
        request: MediaRequest,
        progress_cb,
        cancel_event: threading.Event,
        engine_factory: EngineFactory | None = None,
        journal: TranscriptJournal | None = None,
    ):
        self._request = request
        self._progress_cb = progress_cb
        self._cancel_event = cancel_event
        self._engine_factory = engine_factory or default_engine_factory
        self._journal = journal or TranscriptJournal(warn=lambda message: self._notify(events.NOTE, message))
        self._model_signature = model_signature(request.engine.model_dir)

    def run(self) -> MediaResult:
        self._check_inputs()
        kept, language = self._plan_resume()
        engine = self._load_engine()
        self._raise_if_cancelled()
        segments, info, duration = self._transcribe(engine, kept, language)
        if not plain_text(segments):
            self._journal.drop(self._request.media_path)
            raise NoSpeechError("No speech was detected in this file.")
        return self._save(segments, info, duration, resumed=len(kept), language_given=language is not None)

    # ── Steps ─────────────────────────────────────────────────────────

    def _notify(self, kind: str, *args) -> None:
        if self._progress_cb:
            self._progress_cb(kind, *args)

    def _raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise TranscriptionCancelledError()

    def _check_inputs(self) -> None:
        if not os.path.isfile(self._request.media_path):
            raise RuntimeError(f"File not found: {os.path.basename(self._request.media_path)}")
        problems = problems_with_model_dir(self._request.engine.model_dir)
        if problems:
            raise RuntimeError(f"The speech model is not usable: {problems[0]}. Open Speech Settings to fix it.")

    def _plan_resume(self) -> tuple[list[Segment], str | None]:
        """(segments to keep from an interrupted run, the language to use)."""
        language = self._request.settings.language
        if not self._request.settings.resume:
            return [], language
        partial, why_not = self._journal.load(self._request.media_path, self._model_signature, language)
        if why_not:
            self._notify(events.NOTE, f"Saved progress not reused: {why_not}.")
        if partial is None:
            return [], language
        kept = plan_resume(partial.segments, partial.carried)
        if not kept:
            return [], language
        self._notify(events.NOTE, "Note: the join point of a resumed transcription can occasionally cut or repeat a word.")
        return kept, partial.language

    def _load_engine(self) -> WhisperEngine:
        self._notify(events.STAGE, "Loading the speech model…")
        return self._engine_factory(self._request.engine, lambda message: self._notify(events.NOTE, message))

    def _audio_for(self, engine: WhisperEngine, offset: float):
        """The media path, or — when continuing — the samples from *offset* on."""
        if not offset:
            return self._request.media_path
        return engine.load_audio(self._request.media_path)[int(offset * SAMPLE_RATE):]

    def _transcribe(
        self, engine: WhisperEngine, kept: list[Segment], language: str | None,
    ) -> tuple[list[Segment], StreamInfo, float]:
        offset = kept[-1].end if kept else 0.0
        self._notify(events.STAGE, "Transcribing…")
        info, stream = engine.transcribe(self._audio_for(engine, offset), language, offset)
        self._notify(events.LANGUAGE, info.language, None if language else info.language_probability)

        duration = offset + info.duration
        segments = list(kept)
        writer = self._journal.start(self._request.media_path, self._model_signature, info.language, kept)
        try:
            self._collect(stream, segments, writer, duration)
        finally:
            writer.close()
        return segments, info, duration

    def _collect(self, stream, segments: list[Segment], writer: JournalWriter, duration: float) -> None:
        for segment in stream:
            self._raise_if_cancelled()
            segments.append(segment)
            writer.append(segment)
            self._notify(events.PROGRESS, min(segment.end, duration), duration, segment.text.strip())

    def _save(
        self, segments: list[Segment], info: StreamInfo, duration: float, resumed: int, language_given: bool,
    ) -> MediaResult:
        self._notify(events.STAGE, "Saving…")
        settings = self._request.settings
        write_atomically(
            self._request.output_path,
            render(segments, settings.output_format, settings.timestamps, settings.text_layout),
        )
        self._journal.drop(self._request.media_path)
        return MediaResult(
            output_path=self._request.output_path,
            text=render_text(segments, layout=settings.text_layout).strip(),
            language=info.language,
            language_probability=None if language_given else info.language_probability,
            duration=duration,
            segment_count=len(segments),
            resumed_segments=resumed,
        )


def run_media_transcription(
    request: MediaRequest,
    progress_cb,
    cancel_event: threading.Event,
    engine_factory: EngineFactory | None = None,
    journal: TranscriptJournal | None = None,
) -> MediaResult:
    """
    Transcribes request.media_path and writes the transcript to request.output_path.

    :param progress_cb:  progress_cb(kind, *args) — see core/media/events.py.
    :param cancel_event: when set, the run stops with TranscriptionCancelledError
                         (between segments), keeping its saved progress.
    """
    return MediaTranscription(request, progress_cb, cancel_event, engine_factory, journal).run()


__all__ = ["MediaTranscription", "run_media_transcription"]
