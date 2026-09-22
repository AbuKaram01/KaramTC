# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/constants.py — Named limits and vocabulary of the book pipeline.
"""
from __future__ import annotations

# ── Page types ──────────────────────────────────────────────────────
PAGE_TEXT = "text"      # has reliable native text, extracted directly
PAGE_IMAGE = "image"    # scanned / too little text / garbled — needs OCR

# Pages with fewer extracted characters than this are treated as image/scanned pages
TEXT_PAGE_MIN_CHARS = 100

# A page whose native text is made up of at least this share of unusable
# characters (replacement chars, private-use glyphs, control codes) is treated
# as having a broken text layer — see classification.native_text_looks_garbled().
GARBLED_TEXT_MAX_RATIO = 0.10

# ── How the PDF tab decides, per page, between native text and OCR ──
IMAGE_MODE_AUTO = "auto"    # native text where it looks reliable, OCR for scanned/garbled pages
IMAGE_MODE_ON = "on"        # force image mode: convert every page to an image and OCR it
IMAGE_MODE_OFF = "off"      # never OCR: use only the native text the PDF already contains
IMAGE_MODES = (IMAGE_MODE_AUTO, IMAGE_MODE_ON, IMAGE_MODE_OFF)

# ── Output formats ──────────────────────────────────────────────────
OUTPUT_TXT = "txt"
OUTPUT_PDF = "pdf"
OUTPUT_BOTH = "both"

# ── Rendering ───────────────────────────────────────────────────────
PDF_POINTS_PER_INCH = 72.0

# Rendering a page to an image needs roughly 3 bytes per pixel (several times
# that with "enhance contrast"), so a huge page at a high DPI — a poster, an
# A0 plan at 600 DPI — could exhaust memory, and Tesseract itself refuses
# images with a very long side. Pages that would exceed either limit are
# rendered at a proportionally lower DPI instead of failing.
MAX_RENDER_PIXELS = 64_000_000
MAX_RENDER_SIDE = 20_000

A4_PAGE_SIZE_POINTS = (595, 842)    # placeholder page when nothing else can be recovered

# ── File names ──────────────────────────────────────────────────────
# Longest file-name stem used for outputs and working files. Linux allows 255
# *bytes* per name and the longest derived name adds ~20 bytes of prefix/
# suffix, while Arabic and other non-Latin letters take 2-3 bytes each — so a
# long book title could otherwise make saving fail with "File name too long".
MAX_NAME_BYTES = 150

# ── Failure tolerance ───────────────────────────────────────────────
# One page that can't be read must not sink a 500-page job: it is retried once
# at a lower resolution, and if it still fails it is recorded and skipped. But
# if this many pages fail IN A ROW, it is almost certainly not the pages — OCR
# language, memory, Tesseract itself — so the job stops (and those pages are
# rolled back so a resume retries them) instead of producing a book of
# placeholders after hours of work.
MAX_CONSECUTIVE_PAGE_FAILURES = 5
RETRY_DPI_RANGE = (100, 150)    # the lower-resolution retry never goes outside this
RETRY_DPI_FACTOR = 0.6          # most page-level failures are a huge image running out of time or memory
