# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Vocabulary of the audio/video transcription pipeline.

Defines the accepted file types, output formats, text layouts, model sources and processing devices.
"""
from __future__ import annotations

# File extensions (lower case, with the dot) that are accepted as audio or video input.
AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".wav", ".m4a", ".flac", ".ogg", ".oga", ".opus", ".aac", ".wma",
    ".aiff", ".aif", ".amr", ".mka", ".weba",
})
VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v",
    ".mpg", ".mpeg", ".ts", ".3gp", ".ogv",
})
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

# Output file formats.
OUTPUT_TXT = "txt"
OUTPUT_SRT = "srt"
OUTPUT_VTT = "vtt"
OUTPUT_FORMATS = (OUTPUT_TXT, OUTPUT_SRT, OUTPUT_VTT)
OUTPUT_EXTENSIONS = {OUTPUT_TXT: ".txt", OUTPUT_SRT: ".srt", OUTPUT_VTT: ".vtt"}

# How the text file is laid out.
# Everything as one flowing text.
TEXT_LAYOUT_CONTINUOUS = "continuous"
# One line per spoken segment (can carry start times).
TEXT_LAYOUT_LINES = "lines"
TEXT_LAYOUTS = (TEXT_LAYOUT_CONTINUOUS, TEXT_LAYOUT_LINES)

# Sample rate in Hz that Whisper models work at; faster-whisper decodes everything to this.
SAMPLE_RATE = 16000

# --- Speech model sources ---
# The Whisper model KaramTC downloads and keeps itself.
SOURCE_MANAGED = "managed"
# A faster-whisper (CTranslate2) model folder the user already has.
SOURCE_CUSTOM = "custom"
MODEL_SOURCES = (SOURCE_MANAGED, SOURCE_CUSTOM)

# --- Processing device ---
DEVICE_AUTO = "auto"
DEVICE_CPU = "cpu"
DEVICE_GPU = "gpu"
DEVICES = (DEVICE_AUTO, DEVICE_CPU, DEVICE_GPU)
