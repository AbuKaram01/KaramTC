# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/registry.py — Finds an OCR provider by id and runs it.
"""
from __future__ import annotations

import importlib
import os

from providers.ocr_types import OcrOptions, OcrPageError, OcrResult


def _load_provider_ocr(provider_id: str):
    """Imports `providers.<provider_id>` and returns its ocr() function."""
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
    """
    Runs OCR on one image with the given provider and language.

    :param lang:          Language code passed to the provider (e.g. "ara+eng").
    :param progress_cb:   Optional callback receiving status messages.
    :param cancel_event:  Optional threading.Event; when set, the provider
                          should stop as soon as practical.
    :param options:       Optional advanced engine settings (see OcrOptions).

    OcrPageError (a failure of this one image) is re-raised as is; any other
    exception becomes a RuntimeError carrying its message.
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
