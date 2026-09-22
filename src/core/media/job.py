# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/job.py — What one transcription is asked to do, and what it returns.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.media.constants import DEVICE_AUTO, OUTPUT_TXT, TEXT_LAYOUT_CONTINUOUS


@dataclass(frozen=True)
class EngineSettings:
    """How the speech model is loaded."""
    model_dir: str
    device: str = DEVICE_AUTO       # "auto" | "cpu" | "gpu"
    cpu_threads: int = 4


@dataclass(frozen=True)
class MediaSettings:
    """
    language: Whisper language code, or None to detect it from the audio.
    text_layout: text output only — "continuous" (one flowing text) or "lines"
        (one line per spoken segment).
    timestamps: text output in the "lines" layout only — start each line with its time.
    resume: continue an interrupted transcription of the same file. Off by
        default: the join point can occasionally cut or repeat a word.
    """
    language: str | None = None
    output_format: str = OUTPUT_TXT
    text_layout: str = TEXT_LAYOUT_CONTINUOUS
    timestamps: bool = False
    resume: bool = False


@dataclass(frozen=True)
class MediaRequest:
    media_path: str
    output_path: str
    settings: MediaSettings
    engine: EngineSettings


@dataclass
class MediaResult:
    output_path: str
    text: str                           # the transcript as plain text (for copying), in the chosen layout
    language: str
    language_probability: float | None  # None when the language was given, not detected
    duration: float                     # seconds of audio
    segment_count: int
    resumed_segments: int = 0           # how many came from an earlier, interrupted run
