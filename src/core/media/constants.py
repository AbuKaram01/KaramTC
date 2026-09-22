# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/constants.py — Vocabulary of the audio/video transcription pipeline.
"""
from __future__ import annotations

AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".aac", ".wma",
    ".aiff", ".aif", ".amr", ".mka", ".weba",
})
VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v",
    ".mpg", ".mpeg", ".ts", ".3gp", ".ogv",
})
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

OUTPUT_TXT = "txt"
OUTPUT_SRT = "srt"
OUTPUT_VTT = "vtt"
OUTPUT_FORMATS = (OUTPUT_TXT, OUTPUT_SRT, OUTPUT_VTT)
OUTPUT_EXTENSIONS = {OUTPUT_TXT: ".txt", OUTPUT_SRT: ".srt", OUTPUT_VTT: ".vtt"}

# How the text file is laid out
TEXT_LAYOUT_CONTINUOUS = "continuous"   # everything as one flowing text
TEXT_LAYOUT_LINES = "lines"             # one line per spoken segment (can carry start times)
TEXT_LAYOUTS = (TEXT_LAYOUT_CONTINUOUS, TEXT_LAYOUT_LINES)

SAMPLE_RATE = 16000     # what Whisper models work at; faster-whisper decodes everything to this

# ── Speech model sources ────────────────────────────────────────────
SOURCE_MANAGED = "managed"      # the Whisper model KaramTC downloads and keeps itself
SOURCE_CUSTOM = "custom"        # a faster-whisper (CTranslate2) model folder the user already has
MODEL_SOURCES = (SOURCE_MANAGED, SOURCE_CUSTOM)

# ── Processing device ───────────────────────────────────────────────
DEVICE_AUTO = "auto"
DEVICE_CPU = "cpu"
DEVICE_GPU = "gpu"
DEVICES = (DEVICE_AUTO, DEVICE_CPU, DEVICE_GPU)
