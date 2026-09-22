# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media — Audio and video → text, with Whisper (no GTK).

Typical use:
    request = MediaRequest(path, output_path_for(path, None, "txt"), MediaSettings(), EngineSettings(model_dir))
    result = run_media_transcription(request, progress_cb, cancel_event)
"""
from core.media import events
from core.media.constants import (
    DEVICE_AUTO, DEVICE_CPU, DEVICE_GPU, DEVICES, MEDIA_EXTENSIONS, MODEL_SOURCES, OUTPUT_FORMATS,
    OUTPUT_SRT, OUTPUT_TXT, OUTPUT_VTT, SOURCE_CUSTOM, SOURCE_MANAGED,
)
from core.media.engine import speech_engine_installed
from core.media.errors import (
    DownloadCancelledError, MediaReadError, NoSpeechError, SpeechEngineMissingError,
    TranscriptionCancelledError,
)
from core.media.extraction import run_media_transcription
from core.media.job import EngineSettings, MediaRequest, MediaResult, MediaSettings
from core.media.languages import WHISPER_LANGUAGES, language_name, languages_by_name
from core.media.output import output_path_for
from core.media.probe import MediaInfo, probe_media
from core.media.segments import format_clock

__all__ = [
    "DEVICES", "DEVICE_AUTO", "DEVICE_CPU", "DEVICE_GPU", "DownloadCancelledError", "EngineSettings",
    "MEDIA_EXTENSIONS", "MODEL_SOURCES", "MediaInfo", "MediaReadError", "MediaRequest", "MediaResult",
    "MediaSettings", "NoSpeechError", "OUTPUT_FORMATS", "OUTPUT_SRT", "OUTPUT_TXT",
    "OUTPUT_VTT", "SOURCE_CUSTOM", "SOURCE_MANAGED", "SpeechEngineMissingError", "TranscriptionCancelledError",
    "WHISPER_LANGUAGES", "events", "format_clock", "language_name", "languages_by_name", "output_path_for",
    "probe_media", "run_media_transcription", "speech_engine_installed",
]
