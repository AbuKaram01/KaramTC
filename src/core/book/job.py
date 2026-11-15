# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""What one extraction is asked to do, and what it returns.

The settings are saved into the progress record as flat JSON keys, and a resumed job keeps using the values it
started with. The two conversion functions at the end of the module implement this.
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
    """Everything the user can choose for one extraction.

    Attributes:
        lang: The OCR language.
        page_numbers: Whether the text output marks each page with a "----- Page N -----" line.
        enhance_contrast: Whether the rendered page images get an automatic contrast adjustment before OCR.
        image_mode: "auto" uses native text where it is reliable and OCR for scanned or garbled pages. "on"
            converts every page to an image and runs OCR on it, which is useful when native text comes out
            garbled in a way the detector misses. "off" never runs OCR and uses native text only (fastest).
        dpi: Resolution at which scanned pages are rendered for OCR, clamped to its allowed range. Saved with the
            job.
        jpg_quality: JPEG quality of the rendered pages, clamped to its allowed range. This is also the image
            quality of scanned pages in a searchable PDF. Saved with the job.
        output_format: "txt", "pdf" (a single searchable PDF, no .txt left behind) or "both".
        engine: Advanced tuning options of the OCR engine.
        excluded_pages: Zero-based indices of pages to skip entirely. They are not classified, converted or run
            through OCR, and they are absent from every output. Page numbers in the output ("----- Page N -----",
            error messages) still refer to the original book, so they stay meaningful even with gaps.
        cpu_threads: Upper limit on the number of OCR threads, or None for the engine default. It only affects
            speed, so it is NOT saved with the job: a resumed run uses whatever is passed now.
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
        """Whether the output format includes the .txt file."""
        return self.output_format in (OUTPUT_TXT, OUTPUT_BOTH)

    @property
    def wants_searchable_pdf(self) -> bool:
        """Whether the output format includes the searchable PDF."""
        return self.output_format in (OUTPUT_PDF, OUTPUT_BOTH)


@dataclass
class BookRequest:
    """Everything needed to run one extraction: the source PDF, the OCR provider, the output paths and the settings."""

    pdf_path: str
    # Identifier of the OCR provider, for example "tesseract".
    provider: str
    paths: BookPaths
    settings: BookJobSettings


@dataclass
class BookResult:
    """The return value of run_book_extraction()."""

    # None unless the output format included text.
    txt_path: str | None
    # None unless the output format included a searchable PDF.
    pdf_path: str | None
    total_pages: int
    # How many of total_pages went through OCR.
    ocr_pages: int
    # Mean OCR confidence (0-100) across the OCR'd pages, or None.
    avg_confidence: float | None
    # Image mode "off" only: pages with little or unreliable native text that were NOT OCR'd, so they may be empty
    # or garbled.
    low_text_pages: int = 0
    # {page number (1-based): reason} for pages that could not be read and were left as a placeholder instead.
    failed_pages: dict[int, str] = field(default_factory=dict)


def new_progress_record(request: BookRequest, pdf_fingerprint) -> dict:
    """Return the progress data a brand-new job starts with, including the settings it was started with."""
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
    """Return the settings a job actually runs with.

    These are the settings saved in the progress record when the job started, so that a resume is consistent. For
    anything an older progress file did not record, the value from *requested* is used. The number of CPU threads
    is not saved with a job and always comes from *requested*.
    """
    return BookJobSettings(
        lang=data.get("lang", requested.lang or DEFAULT_LANG),
        page_numbers=data.get("page_numbers", requested.page_numbers),
        enhance_contrast=data.get("enhance_contrast", requested.enhance_contrast),
        # Progress files written before the Auto/On/Off dropdown only have the old boolean "force_image_mode".
        # normalize_image_mode understands both forms.
        image_mode=normalize_image_mode(
            data.get("image_mode", data.get("force_image_mode", requested.image_mode))
        ),
        # Jobs saved by an earlier version have no page-image keys, and their images were rendered at the old fixed
        # values. The fallback is therefore the default constants and not the current user setting, so that one
        # book never ends up with pages at two different resolutions.
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
