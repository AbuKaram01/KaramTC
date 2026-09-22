# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract/engine.py — ocr(): the provider entry point.
"""
from __future__ import annotations

import dataclasses
import os
import tempfile

from providers.ocr_types import OcrOptions, OcrResult
from providers.tesseract.ascii_paths import safe_arguments
from providers.tesseract.command import build_command
from providers.tesseract.failures import check_osd_data_before_running, raise_for_failure
from providers.tesseract.image_prep import ocr_timeout, upright_copy
from providers.tesseract.install import install_hint, is_installed
from providers.tesseract.languages import DEFAULT_LANG
from providers.tesseract.options import normalize_psm
from providers.tesseract.output import read_result
from providers.tesseract.process import run_tesseract


def ocr(image_path: str, lang: str, progress_cb=None, cancel_event=None, options=None) -> OcrResult:
    """
    Runs Tesseract OCR on one image file (the registry's provider interface).

    :param lang:         Language code, e.g. "ara" or "ara+eng" (default if empty).
    :param progress_cb:  Optional callback receiving status messages.
    :param cancel_event: Optional threading.Event, polled while Tesseract runs
                         so Stop kills the process promptly.
    :param options:      Optional OcrOptions (engine mode, page segmentation,
                         custom -c parameters, alternate tessdata dir, whether
                         to also produce a confidence score / searchable PDF).
    """
    options = options or OcrOptions()
    if not is_installed():
        raise RuntimeError("Tesseract is not installed on this machine.\n" + install_hint())

    lang = (lang or DEFAULT_LANG).strip() or DEFAULT_LANG
    psm = normalize_psm(options.psm)
    check_osd_data_before_running(psm, options.tessdata_dir)

    if progress_cb:
        progress_cb(f"Extracting with Tesseract ({lang})…")

    # Tesseract cannot write to stdout, so it writes its output files into a temp directory.
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_base = os.path.join(tmp_dir, "result")
        # Absolute, so a relative path starting with "-" can't be mistaken for an option.
        image_path = upright_copy(os.path.abspath(image_path), tmp_dir)

        # On Windows Tesseract must not be given a path with non-ASCII letters (see ascii_paths); elsewhere, and for
        # ASCII paths, these are the paths as they are.
        with safe_arguments(image_path, output_base, options.tessdata_dir, tmp_dir) as safe:
            command = build_command(
                safe.image, safe.output_base, lang, psm, dataclasses.replace(options, tessdata_dir=safe.tessdata_dir),
            )
            output = run_tesseract(command, options.threads, ocr_timeout(image_path), cancel_event, cwd=safe.cwd)
        raise_for_failure(output, psm=psm, lang=lang, tessdata_dir=options.tessdata_dir)
        return read_result(output_base, options)
