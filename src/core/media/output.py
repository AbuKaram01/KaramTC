# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/output.py — Where a transcript is saved, and saving it safely.
"""
from __future__ import annotations

import contextlib
import os

from core.media.constants import OUTPUT_EXTENSIONS


def output_path_for(media_path: str, output_dir: str | None, output_format: str) -> str:
    """<media name>.txt|.srt|.vtt, next to the media file unless *output_dir* is given."""
    stem = os.path.splitext(os.path.basename(media_path))[0]
    folder = output_dir or os.path.dirname(os.path.abspath(media_path))
    return os.path.join(folder, stem + OUTPUT_EXTENSIONS[output_format])


def write_atomically(path: str, content: str) -> None:
    """
    Writes under a temporary name and renames, so a crash or power cut can
    never leave a truncated transcript — or replace a good one with half of a
    new one.
    """
    temporary = path + ".part"
    try:
        with open(temporary, "w", encoding="utf-8") as output_file:
            output_file.write(content)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(temporary)
        raise
