# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A quick look inside a media file before transcribing it."""
from __future__ import annotations

from dataclasses import dataclass

from core.media.errors import MediaReadError

# PyAV reports the container duration in microseconds.
_MICROSECONDS = 1_000_000


@dataclass(frozen=True)
class MediaInfo:
    """What the container says about a media file."""

    # Seconds, if the container says.
    duration: float | None
    has_audio: bool


def probe_media(path: str) -> MediaInfo | None:
    """Return the duration and whether there is an audio track to transcribe, read with PyAV.

    PyAV is installed together with faster-whisper. If it is not available, None is returned and the transcription
    itself reports any problem.

    Raises:
        MediaReadError: The file cannot be opened as audio or video.
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
