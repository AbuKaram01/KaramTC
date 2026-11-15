# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Exceptions of the transcription pipeline."""
from __future__ import annotations


class TranscriptionCancelledError(Exception):
    """Raised inside a job when the user pressed Stop; saved progress stays usable."""


class SpeechEngineMissingError(RuntimeError):
    """Raised when the faster-whisper package is not installed."""


class NoSpeechError(RuntimeError):
    """Raised when the media file was read fine but contains no recognisable speech."""


class MediaReadError(RuntimeError):
    """Raised when the file cannot be opened as audio or video (damaged, unsupported, or not media at all)."""


class DownloadCancelledError(Exception):
    """Raised when the user cancelled the model download; the partial file is kept so that it can continue."""
