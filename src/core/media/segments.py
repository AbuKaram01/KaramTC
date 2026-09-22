# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/segments.py — Transcribed segments and how they are written out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.media.constants import OUTPUT_SRT, OUTPUT_TXT, OUTPUT_VTT, TEXT_LAYOUT_CONTINUOUS

# Scripts written without spaces between words: Chinese, Japanese, Thai, Lao,
# Myanmar, Khmer (and their full-width punctuation). Two segments are not
# separated by a space where either side is one of these.
_SPACELESS = re.compile("[\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\uff00-\uffef]")

_MS_PER_SECOND = 1000
_MS_PER_MINUTE = 60 * _MS_PER_SECOND
_MS_PER_HOUR = 60 * _MS_PER_MINUTE


@dataclass(frozen=True)
class Segment:
    start: float    # seconds from the start of the media file
    end: float
    text: str


def format_timestamp(seconds: float, millisecond_separator: str = ",") -> str:
    """
    HH:MM:SS,mmm (SRT) or HH:MM:SS.mmm (WebVTT).

    Works in whole milliseconds, so 59.9996 s becomes 00:01:00,000 and never
    an invalid "00:00:59,1000".
    """
    total_ms = max(0, round(seconds * _MS_PER_SECOND))
    hours, rest = divmod(total_ms, _MS_PER_HOUR)
    minutes, rest = divmod(rest, _MS_PER_MINUTE)
    whole_seconds, millis = divmod(rest, _MS_PER_SECOND)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}{millisecond_separator}{millis:03}"


def format_clock(seconds: float) -> str:
    """H:MM:SS, truncated to whole seconds — for progress text and text timestamps."""
    total = max(0, int(seconds))
    return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _spoken(segments: list[Segment]) -> list[Segment]:
    """The segments that actually contain words (Whisper sometimes emits blank ones)."""
    return [segment for segment in segments if segment.text.strip()]


def plain_text(segments: list[Segment]) -> str:
    return "\n".join(segment.text.strip() for segment in _spoken(segments))


def _joined(texts: list[str]) -> str:
    """The texts as one flowing text: separated by a space, except where the script has none."""
    flowing = ""
    for text in map(str.strip, texts):
        if flowing and not (_SPACELESS.match(flowing[-1]) or _SPACELESS.match(text[0])):
            flowing += " "
        flowing += text
    return re.sub(r"\s+", " ", flowing)


def render_text(
    segments: list[Segment], with_timestamps: bool = False, layout: str = TEXT_LAYOUT_CONTINUOUS,
) -> str:
    """
    The words as text: either one flowing text (the default way to read a
    transcript) or one line per segment, which can start each line with its
    time. Start times only make sense line by line, so they are ignored for
    the flowing layout.
    """
    spoken = _spoken(segments)
    if not spoken:
        return ""
    if layout == TEXT_LAYOUT_CONTINUOUS:
        return _joined([segment.text for segment in spoken]) + "\n"
    lines = [
        f"[{format_clock(segment.start)}] {segment.text.strip()}" if with_timestamps else segment.text.strip()
        for segment in spoken
    ]
    return "\n".join(lines) + "\n"


def _render_cues(segments: list[Segment], separator: str) -> str:
    cues = [
        f"{number}\n{format_timestamp(segment.start, separator)} --> "
        f"{format_timestamp(segment.end, separator)}\n{segment.text.strip()}\n"
        for number, segment in enumerate(_spoken(segments), start=1)
    ]
    return "\n".join(cues)


def render_srt(segments: list[Segment]) -> str:
    return _render_cues(segments, ",")


def render_vtt(segments: list[Segment]) -> str:
    return "WEBVTT\n\n" + _render_cues(segments, ".")


def render(
    segments: list[Segment], output_format: str, with_timestamps: bool = False, layout: str = TEXT_LAYOUT_CONTINUOUS,
) -> str:
    """The file content for *output_format* (one of the OUTPUT_* constants)."""
    if output_format == OUTPUT_SRT:
        return render_srt(segments)
    if output_format == OUTPUT_VTT:
        return render_vtt(segments)
    if output_format == OUTPUT_TXT:
        return render_text(segments, with_timestamps, layout)
    raise ValueError(f"Unknown output format: {output_format!r}")
