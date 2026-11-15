# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The single place where the PDF library (PyMuPDF) is imported.

PyMuPDF is published under two import names. ``pymupdf`` is the current one. ``fitz`` is the historical one: newer
releases still provide it but warn that it will be removed in a future version, while older releases, including the
python3-fitz package on Debian 12, only have ``fitz``. Importing through this module works with both names and keeps
the application working if the old name is removed.

Usage: ``from core.pdf_backend import fitz``.
"""

from __future__ import annotations

try:
    import pymupdf as fitz
except ImportError:  # Older PyMuPDF releases only provide the name "fitz".
    import fitz  # type: ignore[no-redef]

__all__ = ["fitz"]
