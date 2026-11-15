# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Turning the Audio/Video tab's state into a job to run.

The module contains plain functions and no widgets.
"""

from __future__ import annotations

import contextlib
import os

from core.media import MediaRequest, MediaSettings, output_path_for
from ui import saved_settings


def problem_blocking_start(model_ready: bool, model_message: str) -> str | None:
    """Return why transcription cannot start right now (a message for the user), or None."""
    if not model_ready:
        return f"{model_message} — open Speech Settings to set it up"
    return None


def output_folder_is_usable(folder: str) -> bool:
    """Create *folder* if needed and return whether files can be written into it."""
    with contextlib.suppress(OSError):
        os.makedirs(folder, exist_ok=True)
    return os.path.isdir(folder) and os.access(folder, os.W_OK | os.X_OK)


def build_request(media_path: str, output_dir: str | None, options) -> MediaRequest:
    """Capture everything the worker needs in a MediaRequest.

    Args:
        media_path: The recording to transcribe.
        output_dir: The folder for the transcript, or None to save next to the recording.
        options: The tab's MediaOptions (language, format, text layout, timestamps).
    """
    settings = MediaSettings(
        language=options.language,
        output_format=options.output_format,
        text_layout=options.text_layout,
        timestamps=options.timestamps,
        resume=bool(saved_settings.speech_resume_enabled()),
    )
    return MediaRequest(
        media_path,
        output_path_for(media_path, output_dir, options.output_format),
        settings,
        saved_settings.read_speech_engine_settings(),
    )
