# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/media_tab/job_setup.py — Turning the Audio/Video tab's state into a job to run.

Plain functions, no widgets.
"""
from __future__ import annotations

import contextlib
import os

from core.media import MediaRequest, MediaSettings, output_path_for
from ui import saved_settings


def problem_blocking_start(model_ready: bool, model_message: str) -> str | None:
    """Why transcription can't start right now (a message for the user), or None."""
    if not model_ready:
        return f"{model_message} — open Speech Settings to set it up"
    return None


def output_folder_is_usable(folder: str) -> bool:
    """Creates *folder* if needed; True if files can be written into it."""
    with contextlib.suppress(OSError):
        os.makedirs(folder, exist_ok=True)
    return os.path.isdir(folder) and os.access(folder, os.W_OK | os.X_OK)


def build_request(media_path: str, output_dir: str | None, options) -> MediaRequest:
    """
    Snapshots everything the worker needs.

    :param options: the tab's MediaOptions (language, format, timestamps).
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
