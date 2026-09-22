# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/job.py — What one extraction is asked to do, and what it returns.

The settings are saved into the progress record as flat JSON keys, and a
resumed job keeps using the values it started with. That is what the two
conversion functions below implement.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from config import BOOK_IMAGE_DPI, BOOK_IMAGE_JPEG_QUALITY
from core.book.constants import IMAGE_MODE_AUTO, OUTPUT_BOTH, OUTPUT_PDF, OUTPUT_TXT
from core.book.normalize import normalize_image_dpi, normalize_image_mode, normalize_jpeg_quality
from core.book.paths import BookPaths
from core.book.progress import STATUS_IN_PROGRESS
from providers.engine_settings import OcrEngineSettings
from providers.tesseract import DEFAULT_LANG


@dataclass
class BookJobSettings:
    """
    Everything the user can choose for one extraction.

    image_mode: "auto" — native text where reliable, OCR for scanned or
        garbled pages. "on" — every page is converted to an image and OCR'd
        (useful when native text comes out garbled in a way the detector
        misses). "off" — never OCR: native text only (fastest).
    dpi / jpg_quality: how scanned pages are rendered for OCR (clamped to
        their allowed ranges). Also the image quality of scanned pages in a
        searchable PDF. Saved with the job.
    output_format: "txt", "pdf" (a single searchable PDF, no .txt left
        behind) or "both".
    excluded_pages: 0-indexed pages to skip entirely — not classified,
        converted or OCR'd, and absent from every output. Page numbers in the
        output ("----- Page N -----", error messages) still refer to the
        original book, so they stay meaningful even with gaps.
    cpu_threads: upper limit on OCR threads (None = engine default). Only
        affects speed, so it is NOT saved with the job: a resumed run uses
        whatever is passed now.
    """
    lang: str
    page_numbers: bool = True
    enhance_contrast: bool = False
    image_mode: str = IMAGE_MODE_AUTO
    dpi: int = BOOK_IMAGE_DPI
    jpg_quality: int = BOOK_IMAGE_JPEG_QUALITY
    output_format: str = OUTPUT_TXT
    engine: OcrEngineSettings = field(default_factory=OcrEngineSettings)
    excluded_pages: set[int] = field(default_factory=set)
    cpu_threads: int | None = None

    @property
    def wants_text(self) -> bool:
        return self.output_format in (OUTPUT_TXT, OUTPUT_BOTH)

    @property
    def wants_searchable_pdf(self) -> bool:
        return self.output_format in (OUTPUT_PDF, OUTPUT_BOTH)


@dataclass
class BookRequest:
    pdf_path: str
    provider: str
    paths: BookPaths
    settings: BookJobSettings


@dataclass
class BookResult:
    """Return value of run_book_extraction()."""
    txt_path: str | None            # None unless the format included text
    pdf_path: str | None            # None unless the format included a searchable PDF
    total_pages: int
    ocr_pages: int                  # how many of total_pages went through OCR
    avg_confidence: float | None    # mean OCR confidence (0-100) across OCR'd pages, or None
    low_text_pages: int = 0         # image mode "off" only: pages with little/unreliable native
                                    # text that were NOT OCR'd, so may be empty or garbled
    failed_pages: dict[int, str] = field(default_factory=dict)
                                    # {page number (1-based): reason} for pages that could not be
                                    # read and were left as a placeholder instead


def new_progress_record(request: BookRequest, pdf_fingerprint) -> dict:
    """The progress data a brand-new job starts with."""
    settings, engine = request.settings, request.settings.engine
    return {
        "pdf_path":                  request.pdf_path,
        "pdf_name":                  os.path.basename(request.pdf_path),
        "pdf_fingerprint":           pdf_fingerprint,
        "provider":                  request.provider,
        "lang":                      settings.lang,
        "total_pages":               0,
        "completed_pages":           0,
        "page_types":                None,
        "page_numbers":              settings.page_numbers,
        "enhance_contrast":          settings.enhance_contrast,
        "image_mode":                normalize_image_mode(settings.image_mode),
        "image_dpi":                 normalize_image_dpi(settings.dpi),
        "jpeg_quality":              normalize_jpeg_quality(settings.jpg_quality),
        "output_format":             settings.output_format,
        "oem":                       engine.oem,
        "psm":                       engine.psm,
        "preserve_interword_spaces": engine.preserve_interword_spaces,
        "custom_params":             engine.custom_params,
        "lang_source":               engine.lang_source,
        "excluded_pages":            sorted(settings.excluded_pages),
        "tess_extra":                dict(engine.extra_variables),
        "ocr_confidences":           [],
        "status":                    STATUS_IN_PROGRESS,
    }


def settings_from_progress(data: dict, requested: BookJobSettings) -> BookJobSettings:
    """
    The settings a job actually runs with: those saved when it started (so a
    resume is consistent), falling back to *requested* for anything an older
    progress file did not record.
    """
    return BookJobSettings(
        lang=data.get("lang", requested.lang or DEFAULT_LANG),
        page_numbers=data.get("page_numbers", requested.page_numbers),
        enhance_contrast=data.get("enhance_contrast", requested.enhance_contrast),
        # Progress files written before the Auto/On/Off dropdown only have the
        # old boolean "force_image_mode" — normalize_image_mode understands both.
        image_mode=normalize_image_mode(
            data.get("image_mode", data.get("force_image_mode", requested.image_mode))
        ),
        # Jobs saved by an earlier version have no page-image keys, and their
        # images were rendered at the old fixed values — resume at those, not
        # at whatever the setting happens to be now, so one book never ends up
        # with pages at two different resolutions.
        dpi=normalize_image_dpi(data.get("image_dpi", BOOK_IMAGE_DPI)),
        jpg_quality=normalize_jpeg_quality(data.get("jpeg_quality", BOOK_IMAGE_JPEG_QUALITY)),
        output_format=data.get("output_format", requested.output_format),
        engine=OcrEngineSettings(
            oem=data.get("oem", requested.engine.oem),
            psm=data.get("psm", requested.engine.psm),
            preserve_interword_spaces=data.get(
                "preserve_interword_spaces", requested.engine.preserve_interword_spaces),
            custom_params=data.get("custom_params", requested.engine.custom_params),
            lang_source=data.get("lang_source", requested.engine.lang_source),
            extra_variables=data.get("tess_extra", dict(requested.engine.extra_variables)),
        ),
        excluded_pages=set(data.get("excluded_pages", sorted(requested.excluded_pages))),
        cpu_threads=requested.cpu_threads,
    )
