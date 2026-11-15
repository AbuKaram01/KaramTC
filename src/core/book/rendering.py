# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Rendering of scanned PDF pages to JPEG images for OCR."""

from __future__ import annotations

import importlib
import math
import os
import threading
from dataclasses import dataclass, replace

from core.book import events
from core.book.constants import MAX_RENDER_PIXELS, MAX_RENDER_SIDE, PDF_POINTS_PER_INCH
from core.book.errors import CancelledError
from core.book.pdf_io import open_pdf, require_fitz
from core.book.workdir import page_image_path, part_path, remove_quietly


@dataclass(frozen=True)
class RenderSettings:
    """How a page is rendered to an image: resolution, JPEG quality and optional contrast enhancement."""

    dpi: int
    jpg_quality: int
    enhance_contrast: bool = False


def short_reason(exc) -> str:
    """Return the first line of an error message, shortened to 140 characters, for placeholders and summaries."""
    max_length = 140
    line = (str(exc).strip().splitlines() or [type(exc).__name__])[0].strip()
    return line if len(line) <= max_length else line[: max_length - 3] + "…"


def render_scale(rect, dpi: int) -> float:
    """Return the zoom factor for rendering a page of size *rect* (in PDF points) at *dpi*.

    The factor is lowered when the image would exceed MAX_RENDER_PIXELS or MAX_RENDER_SIDE. See those constants
    for the reason.
    """
    scale = dpi / PDF_POINTS_PER_INCH
    width = max(rect.width, 1.0) * scale
    height = max(rect.height, 1.0) * scale
    factor = 1.0
    if width * height > MAX_RENDER_PIXELS:
        factor = min(factor, math.sqrt(MAX_RENDER_PIXELS / (width * height)))
    if max(width, height) > MAX_RENDER_SIDE:
        factor = min(factor, MAX_RENDER_SIDE / max(width, height))
    return scale * factor


class PageImageRenderer:
    """Converts pages of one PDF into compressed JPEGs inside a working folder.

    Args:
        pdf_path: The PDF to render.
        images_dir: The working folder that receives the images.
        settings: Resolution, quality and contrast options.
        cancel_event: When set, rendering stops with CancelledError before the next page.
    """

    def __init__(
        self,
        pdf_path: str,
        images_dir: str,
        settings: RenderSettings,
        cancel_event: threading.Event | None = None,
    ):
        self.pdf_path = pdf_path
        self.images_dir = images_dir
        self.settings = settings
        self.cancel_event = cancel_event

    def at_dpi(self, dpi: int) -> PageImageRenderer:
        """Return the same renderer at another resolution."""
        return PageImageRenderer(self.pdf_path, self.images_dir, replace(self.settings, dpi=dpi), self.cancel_event)

    def render(
        self,
        page_indices: list[int],
        progress_cb=None,
        failures: dict[int, str] | None = None,
    ) -> dict[int, str]:
        """Convert the given pages and return ``{page_index: image_path}``.

        The document is opened once and the pages are processed sequentially to keep memory usage low.

        By default a page that cannot be converted aborts the whole call. If a *failures* dict is passed, such
        pages are recorded in it as ``{page_index: reason}`` and skipped instead, so that one damaged page does
        not stop the rest.

        Args:
            page_indices: Zero-based indices of the pages to convert.
            progress_cb: Called as ``progress_cb(events.CONVERT, done, total)`` after each converted page.
            failures: Receives the pages that could not be converted.

        Raises:
            CancelledError: The cancel event was set.
            RuntimeError: A page could not be converted and no *failures* dict was given, or a required library
                is missing.
        """
        if not page_indices:
            return {}
        self._require_libraries()
        os.makedirs(self.images_dir, exist_ok=True)

        results: dict[int, str] = {}
        doc = open_pdf(self.pdf_path)
        try:
            total = len(page_indices)
            for completed, page_index in enumerate(sorted(page_indices), 1):
                self._raise_if_cancelled()
                try:
                    results[page_index] = self._render_page(doc, page_index)
                except Exception as exc:
                    if failures is None:
                        raise RuntimeError(
                            f"Page {page_index + 1} could not be converted to an image: {exc}"
                        ) from exc
                    failures[page_index] = (
                        f"the page could not be converted to an image ({short_reason(exc)})"
                    )
                    continue
                if progress_cb:
                    progress_cb(events.CONVERT, completed, total)
        finally:
            doc.close()
        return results

    def _require_libraries(self) -> None:
        """Check up front that PyMuPDF and, if contrast enhancement is on, Pillow are installed."""
        require_fitz()
        if self.settings.enhance_contrast:
            try:
                importlib.import_module("PIL.ImageOps")
            except ImportError:
                raise RuntimeError("Pillow is not installed.\nRun: pip install Pillow")

    def _raise_if_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise CancelledError()

    def _render_page(self, doc, page_index: int) -> str:
        """Render one page and return the path of its image.

        The JPEG is written under a temporary name and renamed when it is complete, so that a crash or power loss
        can never leave a half-written image under the real name for a later resume to pick up and feed to OCR.
        """
        fitz = require_fitz()
        image_path = page_image_path(self.images_dir, page_index)
        temporary = part_path(image_path)
        try:
            page = doc.load_page(page_index)
            scale = render_scale(page.rect, self.settings.dpi)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            self._save_jpeg(pixmap, temporary)
            os.replace(temporary, image_path)
        except Exception:
            remove_quietly(temporary)
            raise
        return image_path

    def _save_jpeg(self, pixmap, path: str) -> None:
        """Save *pixmap* as a JPEG, applying an automatic contrast adjustment first if that is enabled."""
        quality = self.settings.jpg_quality
        if not self.settings.enhance_contrast:
            pixmap.save(path, output="jpeg", jpg_quality=quality)
            return
        # Pillow is needed only for contrast enhancement; _require_libraries has already checked that it is
        # installed.
        from PIL import Image, ImageOps
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        ImageOps.autocontrast(image, cutoff=1).save(path, "JPEG", quality=quality)
