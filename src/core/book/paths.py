# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The locations of a book's outputs and working files."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from core.book.constants import MAX_NAME_BYTES

# Characters that are not allowed in a file name on Windows, plus control characters.
_ILLEGAL_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_HASH_SUFFIX_LENGTH = 8


def sanitize_filename(name: str) -> str:
    """Return a safe file-name stem: no path or control characters, at most MAX_NAME_BYTES bytes long."""
    name = _ILLEGAL_FILENAME_CHARS.sub("_", name.strip().strip("."))
    encoded = name.encode("utf-8")
    if len(encoded) > MAX_NAME_BYTES:
        # Cut on a character boundary and append a short hash of the full name, so that two long titles that
        # differ only near the end still map to different output files instead of overwriting each other.
        digest = hashlib.sha1(encoded).hexdigest()[:_HASH_SUFFIX_LENGTH]
        room = MAX_NAME_BYTES - _HASH_SUFFIX_LENGTH - 1
        head = encoded[:room].decode("utf-8", errors="ignore").rstrip(" ._")
        name = f"{head}-{digest}"
    return name or "book"


@dataclass(frozen=True)
class BookPaths:
    """Every path associated with one PDF extraction job."""

    # The sanitized file-name stem.
    base: str
    output_dir: str
    txt_path: str
    # The searchable PDF.
    pdf_path: str
    # The working folder for page images and OCR fragments.
    images_dir: str
    progress_path: str


def book_paths(pdf_path: str, output_dir: str | None) -> BookPaths:
    """Return the output and working paths for *pdf_path*, placed in *output_dir* or next to the PDF if it is None."""
    base = sanitize_filename(os.path.splitext(os.path.basename(pdf_path))[0])
    folder = output_dir or os.path.dirname(os.path.abspath(pdf_path)) or os.getcwd()
    return BookPaths(
        base=base,
        output_dir=folder,
        txt_path=os.path.join(folder, f"{base}.txt"),
        # The name is suffixed and never a bare "{base}.pdf": the source book is itself a PDF that lives in this
        # same folder by default, so an unsuffixed name would silently overwrite the user's original file.
        pdf_path=os.path.join(folder, f"{base}_searchable.pdf"),
        images_dir=os.path.join(folder, f"{base}_pages"),
        progress_path=os.path.join(folder, f".{base}.ocr-progress.json"),
    )
