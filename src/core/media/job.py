# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Value objects that describe what one transcription is asked to do, and what it returns."""
from __future__ import annotations

from dataclasses import dataclass

from core.media.constants import DEVICE_AUTO, OUTPUT_TXT, TEXT_LAYOUT_CONTINUOUS


@dataclass(frozen=True)
class EngineSettings:
    """How the speech model is loaded."""

    model_dir: str
    # One of DEVICES: "auto", "cpu" or "gpu".
    device: str = DEVICE_AUTO
    cpu_threads: int = 4


@dataclass(frozen=True)
class MediaSettings:
    """The user's choices for one transcription.

    Attributes:
        language: Whisper language code, or None to detect it from the audio.
        output_format: One of OUTPUT_FORMATS ("txt", "srt" or "vtt").
        text_layout: Text output only: "continuous" (one flowing text) or "lines" (one line per spoken segment).
        timestamps: Text output in the "lines" layout only: start each line with its time.
        resume: Continue an interrupted transcription of the same file. Off by default: the join point can
            occasionally cut or repeat a word.
    """

    language: str | None = None
    output_format: str = OUTPUT_TXT
    text_layout: str = TEXT_LAYOUT_CONTINUOUS
    timestamps: bool = False
    resume: bool = False


@dataclass(frozen=True)
class MediaRequest:
    """One transcription job: the media file, where the result goes, and how to process it."""

    media_path: str
    output_path: str
    settings: MediaSettings
    engine: EngineSettings


@dataclass
class MediaResult:
    """The outcome of a finished transcription."""

    output_path: str
    # The transcript as plain text (for copying), in the chosen layout.
    text: str
    language: str
    # None when the language was given, not detected.
    language_probability: float | None
    # Seconds of audio.
    duration: float
    segment_count: int
    # How many segments came from an earlier, interrupted run.
    resumed_segments: int = 0
