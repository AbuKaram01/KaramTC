# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/pdf_backend.py — the one place the PDF library is imported.

PyMuPDF is published under two import names. `pymupdf` is the current one;
`fitz` is the historical one, which newer releases still provide but warn
about ("will be removed in future"), while older releases — including the
python3-fitz package on Debian 12 — only have `fitz`. Importing through here
works with both, and a future removal of the old name won't break the app.

Usage:  from core.pdf_backend import fitz
"""
from __future__ import annotations

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz  # type: ignore[no-redef]

__all__ = ["fitz"]
