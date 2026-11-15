# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Find an OCR provider by id and run it."""

from __future__ import annotations

import importlib
import os

from providers.ocr_types import OcrOptions, OcrPageError, OcrResult


def _load_provider_ocr(provider_id: str):
    """Import `providers.<provider_id>` and return its ocr() function."""
    try:
        module = importlib.import_module(f"providers.{provider_id}")
    except ModuleNotFoundError:
        raise RuntimeError(f"No provider found with ID: {provider_id!r}")
    if not hasattr(module, "ocr"):
        raise RuntimeError(f"providers/{provider_id} does not export an ocr() function")
    return module.ocr


def run_ocr(
    image_path: str,
    provider: str,
    lang: str,
    *,
    progress_cb=None,
    cancel_event=None,
    options: OcrOptions | None = None,
) -> OcrResult:
    """Run OCR on one image with the given provider and language.

    Args:
        image_path: The image file to read.
        provider: The id of the provider package under `providers`.
        lang: Language code passed to the provider (e.g. "ara+eng").
        progress_cb: Optional callback receiving status messages.
        cancel_event: Optional threading.Event; when set, the provider should stop as soon as practical.
        options: Optional advanced engine settings (see OcrOptions).

    Returns:
        The recognized text, with confidence and a searchable PDF if the options asked for them.

    Raises:
        OcrPageError: OCR failed for this one image; re-raised unchanged so that a job can skip the page.
        RuntimeError: The image or the provider is missing, or the provider failed in any other way; the message
            of the original exception is kept.
    """
    if not os.path.isfile(image_path):
        raise RuntimeError(f"File not found: {os.path.basename(image_path)}")

    ocr = _load_provider_ocr(provider)
    try:
        return ocr(image_path, lang, progress_cb, cancel_event=cancel_event, options=options)
    except OcrPageError:
        raise
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc
