# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/paths.py — Where a book's outputs and working files live.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from core.book.constants import MAX_NAME_BYTES

_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_HASH_SUFFIX_LENGTH = 8


def sanitize_filename(name: str) -> str:
    """A safe file-name stem: no path or control characters, within MAX_NAME_BYTES."""
    name = _ILLEGAL_FILENAME_CHARS.sub("_", name.strip().strip("."))
    encoded = name.encode("utf-8")
    if len(encoded) > MAX_NAME_BYTES:
        # Cut on a character boundary and append a short hash of the full
        # name, so two long titles that only differ near the end still map to
        # different output files instead of overwriting each other.
        digest = hashlib.sha1(encoded).hexdigest()[:_HASH_SUFFIX_LENGTH]
        room = MAX_NAME_BYTES - _HASH_SUFFIX_LENGTH - 1
        head = encoded[:room].decode("utf-8", errors="ignore").rstrip(" ._")
        name = f"{head}-{digest}"
    return name or "book"


@dataclass(frozen=True)
class BookPaths:
    """Every path associated with one PDF extraction job."""
    base: str               # sanitized file-name stem
    output_dir: str
    txt_path: str
    pdf_path: str           # the searchable PDF
    images_dir: str         # working folder for page images / OCR fragments
    progress_path: str


def book_paths(pdf_path: str, output_dir: str | None) -> BookPaths:
    base = sanitize_filename(os.path.splitext(os.path.basename(pdf_path))[0])
    folder = output_dir or os.path.dirname(os.path.abspath(pdf_path)) or os.getcwd()
    return BookPaths(
        base=base,
        output_dir=folder,
        txt_path=os.path.join(folder, f"{base}.txt"),
        # Suffixed (never bare "{base}.pdf") — the source book is itself a PDF
        # living in this same directory by default, so an unsuffixed name
        # would silently overwrite the user's original file.
        pdf_path=os.path.join(folder, f"{base}_searchable.pdf"),
        images_dir=os.path.join(folder, f"{base}_pages"),
        progress_path=os.path.join(folder, f".{base}.ocr-progress.json"),
    )
