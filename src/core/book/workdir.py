# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/workdir.py — The per-book working folder ("<book>_pages").

It holds one JPEG per scanned page and, for searchable-PDF output, one
single-page PDF fragment per OCR'd page. The folder is named after the book,
so it may pre-exist as an unrelated user folder: only files this app creates
(see _WORK_FILE_PATTERN) are ever touched.
"""
from __future__ import annotations

import contextlib
import os
import re

_WORK_FILE_PATTERN = re.compile(r"^page_\d{5}\.(jpg|pdf)(\.part)?$")
_IMAGE_NAME_PREFIX = "page_"
_IMAGE_NAME_SUFFIX = ".jpg"
_JPEG_END_MARKER = b"\xff\xd9"      # cannot occur inside the compressed data
_JPEG_TAIL_BYTES = 32
_MIN_JPEG_SIZE = 4
_PART_SUFFIX = ".part"


def _page_file_path(images_dir: str, page_index: int, extension: str) -> str:
    return os.path.join(images_dir, f"page_{page_index + 1:05d}.{extension}")


def page_image_path(images_dir: str, page_index: int) -> str:
    return _page_file_path(images_dir, page_index, "jpg")


def page_fragment_path(images_dir: str, page_index: int) -> str:
    return _page_file_path(images_dir, page_index, "pdf")


def part_path(path: str) -> str:
    """Temporary name a file is written under until it is complete."""
    return path + _PART_SUFFIX


def write_bytes_atomically(path: str, content: bytes) -> None:
    """Writes under a temporary name and renames, so a crash never leaves a half-written file."""
    temporary = part_path(path)
    with open(temporary, "wb") as temporary_file:
        temporary_file.write(content)
    os.replace(temporary, path)


def remove_quietly(path: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(path)


def image_is_complete(path: str) -> bool:
    """
    True if *path* is a whole JPEG: non-empty and ending with the JPEG
    end-of-image marker. Catches page images truncated by a crash in a run
    from an earlier version.
    """
    try:
        size = os.path.getsize(path)
        if size < _MIN_JPEG_SIZE:
            return False
        with open(path, "rb") as image_file:
            image_file.seek(max(0, size - _JPEG_TAIL_BYTES))
            return _JPEG_END_MARKER in image_file.read()
    except OSError:
        return False


def _page_index_from_image_name(file_name: str) -> int | None:
    if not (file_name.startswith(_IMAGE_NAME_PREFIX) and file_name.endswith(_IMAGE_NAME_SUFFIX)):
        return None
    try:
        return int(file_name[len(_IMAGE_NAME_PREFIX):-len(_IMAGE_NAME_SUFFIX)]) - 1
    except ValueError:
        return None


def find_complete_page_images(images_dir: str) -> dict[int, str]:
    """
    {page_index: path} of the page images already in the working folder.
    Truncated ones are deleted (and so redone) rather than fed to OCR.
    """
    found: dict[int, str] = {}
    if not os.path.isdir(images_dir):
        return found
    for file_name in os.listdir(images_dir):
        page_index = _page_index_from_image_name(file_name)
        if page_index is None:
            continue
        full_path = os.path.join(images_dir, file_name)
        if image_is_complete(full_path):
            found[page_index] = full_path
        else:
            remove_quietly(full_path)
    return found


def remove_work_dir(images_dir: str) -> None:
    """
    Deletes the working folder's page images/fragments and then the folder —
    but only if nothing else is left in it. Wiping it with rmtree would
    destroy the files of an unrelated user folder that shares the name.
    """
    try:
        names = os.listdir(images_dir)
    except OSError:
        return
    for name in names:
        if _WORK_FILE_PATTERN.match(name):
            remove_quietly(os.path.join(images_dir, name))
    with contextlib.suppress(OSError):
        os.rmdir(images_dir)          # only succeeds when it is now empty
