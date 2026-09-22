# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/probe.py — A quick look inside a media file before transcribing it.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.media.errors import MediaReadError

_MICROSECONDS = 1_000_000


@dataclass(frozen=True)
class MediaInfo:
    duration: float | None      # seconds, if the container says
    has_audio: bool


def probe_media(path: str) -> MediaInfo | None:
    """
    Duration and whether there is an audio track to transcribe, read with PyAV
    (installed together with faster-whisper). None if PyAV is not available —
    the transcription itself then reports any problem.

    Raises MediaReadError if the file cannot be opened as audio or video.
    """
    try:
        import av
    except ImportError:
        return None
    try:
        with av.open(path) as container:
            has_audio = any(stream.type == "audio" for stream in container.streams)
            duration = container.duration / _MICROSECONDS if container.duration else None
    except Exception as exc:
        raise MediaReadError(f"This file could not be read as audio or video ({exc})") from exc
    return MediaInfo(duration, has_audio)
