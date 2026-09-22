# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/events.py — The progress-callback protocol.

The pipeline reports progress by calling  progress_cb(kind, *args)  from its
worker thread. Every kind and the arguments that go with it:

  STAGE        (label)                   a new stage began
  CLASSIFY     (page, total)             analysing page N of the PDF
  CONVERT      (done, total)             converting a scanned page to an image
  DIRECT       (position, total)         extracting a native-text page
  OCR          (position, total)         running OCR on a page
  KEY          (message, position, total) status text from the OCR engine
  PAGE_FAILED  (page_number, reason, failed_so_far)
"""
from __future__ import annotations

STAGE = "stage"
CLASSIFY = "classify"
CONVERT = "convert"
DIRECT = "direct"
OCR = "ocr"
KEY = "key"
PAGE_FAILED = "page_failed"
