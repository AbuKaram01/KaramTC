# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract/failures.py — Turns Tesseract failures into actionable errors.

Two kinds are told apart on purpose (see OcrPageError): setup problems
(missing language or osd data) raise RuntimeError and stop a long job at
once; a failure belonging to one image raises OcrPageError and lets the job
skip that page and carry on.
"""
from __future__ import annotations

import os

from providers import tessdata_manager
from providers.ocr_types import OcrPageError
from providers.tesseract.install import install_hint, osd_install_hint
from providers.tesseract.options import psm_needs_osd
from providers.tesseract.process import ProcessOutput

_PICK_ANOTHER_MODE = "Or pick a page segmentation mode that doesn't need it (e.g. 'Fully automatic')."
_OSD_LOAD_ERROR = "Failed loading language 'osd'"
_LANGUAGE_LOAD_ERRORS = ("Failed loading language", "Could not initialize")


def osd_missing_error(downloaded_data: bool) -> RuntimeError:
    """Actionable error for PSM 1/12 when osd.traineddata cannot be loaded."""
    if downloaded_data:
        return RuntimeError(
            "Orientation detection data (osd) could not be loaded from the downloaded "
            "language data.\n"
            "Download it from OCR Settings \u2192 Manage downloaded languages "
            "\u2014 no admin rights needed.\n" + _PICK_ANOTHER_MODE
        )
    return RuntimeError(
        "Orientation detection data (osd) is not installed on this system.\n"
        f"{osd_install_hint()}\n" + _PICK_ANOTHER_MODE
    )


def check_osd_data_before_running(psm: int, tessdata_dir: str | None) -> None:
    """
    PSM 1/12 need osd.traineddata, which no language pack ships. With a
    downloaded tessdata dir it can be checked up front, failing fast before
    time is spent on OCR. For the system source the problem is detected from
    Tesseract's stderr instead (see raise_for_failure); without either check
    Tesseract only prints a warning and silently skips orientation detection.
    """
    if not (psm_needs_osd(psm) and tessdata_dir):
        return
    osd_file = os.path.join(tessdata_dir, f"{tessdata_manager.OSD_CODE}.traineddata")
    if not os.path.isfile(osd_file):
        raise osd_missing_error(downloaded_data=True)


def _language_data_error(lang: str, tessdata_dir: str | None) -> RuntimeError:
    if tessdata_dir:
        return RuntimeError(
            f"Could not load the downloaded '{lang}' language data.\n"
            "It may be corrupt — try deleting and re-downloading it "
            "from OCR Settings \u2192 Manage downloaded languages."
        )
    return RuntimeError(
        f"Tesseract language pack '{lang}' is not installed.\n"
        "Download it from OCR Settings \u2192 Manage downloaded languages "
        "\u2014 no admin rights needed. Or, as a system package: "
        f"{install_hint(lang.split('+', 1)[0])}"
    )


def raise_for_failure(output: ProcessOutput, *, psm: int, lang: str, tessdata_dir: str | None) -> None:
    """Raises the right error if Tesseract did not finish successfully."""
    stderr = output.stderr or ""
    if psm_needs_osd(psm) and _OSD_LOAD_ERROR in stderr:
        raise osd_missing_error(downloaded_data=bool(tessdata_dir))
    if output.returncode == 0:
        return

    details = stderr.strip()
    if any(marker in details for marker in _LANGUAGE_LOAD_ERRORS):
        raise _language_data_error(lang, tessdata_dir)
    # Setup problems were handled above; what is left — a crash, being killed
    # for memory, an unreadable image — belongs to this one image.
    raise OcrPageError(f"Tesseract failed: {details or f'exit code {output.returncode}'}")
