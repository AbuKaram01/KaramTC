# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Read the files Tesseract wrote for one image."""

from __future__ import annotations

import os

from providers.ocr_types import OcrOptions, OcrPageError, OcrResult

# Structural rows (page, block, paragraph, line) carry conf == -1, so a real word's score is never below this.
_MIN_WORD_CONFIDENCE = 0


def parse_mean_confidence(tsv_path: str) -> float | None:
    """Return the mean word confidence (0-100) from Tesseract's TSV output.

    The result is None if the file is missing, malformed, or has no recognized words. Structural rows (page, block,
    paragraph, line) carry conf == -1 and are excluded.
    """
    try:
        with open(tsv_path, encoding="utf-8") as tsv_file:
            lines = tsv_file.read().splitlines()
    except OSError:
        return None
    if len(lines) < 2:
        return None
    try:
        conf_column = lines[0].split("\t").index("conf")
    except ValueError:
        return None

    scores = []
    for line in lines[1:]:
        columns = line.split("\t")
        if len(columns) <= conf_column:
            continue
        try:
            score = float(columns[conf_column])
        except ValueError:
            continue
        if score >= _MIN_WORD_CONFIDENCE:
            scores.append(score)
    return sum(scores) / len(scores) if scores else None


def _read_text(path: str) -> str:
    """Return the stripped text of the file at *path*; undecodable bytes are replaced."""
    with open(path, encoding="utf-8", errors="replace") as text_file:
        return text_file.read().strip()


def _read_bytes_if_present(path: str) -> bytes | None:
    """Return the content of the file at *path*, or None if it does not exist."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as binary_file:
        return binary_file.read()


def read_result(output_base: str, options: OcrOptions) -> OcrResult:
    """Collect the text, confidence and searchable PDF from <output_base>.{txt,tsv,pdf}.

    Raises:
        OcrPageError: Tesseract wrote no text file.
    """
    text_path = output_base + ".txt"
    if not os.path.exists(text_path):
        raise OcrPageError("Tesseract did not produce any output file")
    text = _read_text(text_path)

    confidence = None
    if options.want_confidence:
        confidence = parse_mean_confidence(output_base + ".tsv")
        # A page without any text counts as zero confidence, whatever words the TSV listed; None stays None.
        if not text:
            confidence = 0.0 if confidence is not None else None

    pdf_bytes = _read_bytes_if_present(output_base + ".pdf") if options.want_pdf else None
    return OcrResult(text=text, confidence=confidence, pdf_bytes=pdf_bytes)
