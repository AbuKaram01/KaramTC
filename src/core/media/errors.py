# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/errors.py — Exceptions of the transcription pipeline.
"""
from __future__ import annotations


class TranscriptionCancelledError(Exception):
    """Raised inside a job when the user pressed Stop; saved progress stays usable."""


class SpeechEngineMissingError(RuntimeError):
    """The faster-whisper package is not installed."""


class NoSpeechError(RuntimeError):
    """The media file was read fine but contains no recognisable speech."""


class MediaReadError(RuntimeError):
    """The file can't be opened as audio or video (damaged, unsupported, or not media at all)."""


class DownloadCancelledError(Exception):
    """Raised when the user cancelled the model download; the partial file is kept so it can continue."""
