# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Named limits and shared vocabulary of the book pipeline."""

from __future__ import annotations

# --- Page types ---
# A page with reliable native text, which is extracted directly.
PAGE_TEXT = "text"
# A scanned page, a page with too little text or one with a garbled text layer. It needs OCR.
PAGE_IMAGE = "image"

# Pages with fewer extracted characters than this are treated as image (scanned) pages.
TEXT_PAGE_MIN_CHARS = 100

# A page whose native text consists of at least this share of unusable characters (replacement characters,
# private-use glyphs, control codes) is treated as having a broken text layer. See
# classification.native_text_looks_garbled().
GARBLED_TEXT_MAX_RATIO = 0.10

# --- How the PDF tab decides, per page, between native text and OCR ---
# Native text where it looks reliable, OCR for scanned or garbled pages.
IMAGE_MODE_AUTO = "auto"
# Force image mode: convert every page to an image and OCR it.
IMAGE_MODE_ON = "on"
# Never OCR: use only the native text that the PDF already contains.
IMAGE_MODE_OFF = "off"
IMAGE_MODES = (IMAGE_MODE_AUTO, IMAGE_MODE_ON, IMAGE_MODE_OFF)

# --- Output formats ---
OUTPUT_TXT = "txt"
OUTPUT_PDF = "pdf"
OUTPUT_BOTH = "both"

# --- Rendering ---
PDF_POINTS_PER_INCH = 72.0

# Rendering a page to an image needs roughly 3 bytes per pixel (several times that with "enhance contrast"), so a
# huge page at a high DPI, such as a poster or an A0 plan at 600 DPI, could exhaust memory. Tesseract itself also
# refuses images with a very long side. Pages that would exceed either limit are rendered at a proportionally lower
# DPI instead of failing.
MAX_RENDER_PIXELS = 64_000_000
MAX_RENDER_SIDE = 20_000

# Size of the placeholder page used when nothing else can be recovered for a page.
A4_PAGE_SIZE_POINTS = (595, 842)

# --- File names ---
# Longest file-name stem used for outputs and working files. Linux allows 255 *bytes* per name and the longest
# derived name adds about 20 bytes of prefix and suffix, while Arabic and other non-Latin letters take 2-3 bytes
# each. A long book title could otherwise make saving fail with "File name too long".
MAX_NAME_BYTES = 150

# --- Failure tolerance ---
# One page that cannot be read must not sink a 500-page job: it is retried once at a lower resolution and, if it
# still fails, it is recorded and skipped. But if this many pages fail IN A ROW, the cause is almost certainly not
# the pages (OCR language, memory, Tesseract itself), so the job stops instead of producing a book of placeholders
# after hours of work. The pages of that run are rolled back so that a resume retries them.
MAX_CONSECUTIVE_PAGE_FAILURES = 5
# The lower-resolution retry never goes outside this DPI range.
RETRY_DPI_RANGE = (100, 150)
# Most page-level failures are a huge image running out of time or memory, so the retry scales the DPI by this factor.
RETRY_DPI_FACTOR = 0.6
