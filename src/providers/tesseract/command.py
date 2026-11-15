# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Build the `tesseract` command line."""

from __future__ import annotations

from providers.ocr_types import TESSERACT_TOGGLE_VARIABLES, OcrOptions
from providers.tesseract import program
from providers.tesseract.options import normalize_oem


def parse_custom_params(raw: str) -> list[tuple[str, str]]:
    """Parse a free-text "key=value" list into (key, value) pairs, one -c flag each.

    Entries may be separated by semicolons and/or newlines. Blank or malformed entries are skipped rather than
    raising, since this is user-typed advanced config, not a machine-generated format.
    """
    pairs: list[tuple[str, str]] = []
    for chunk in (raw or "").replace("\n", ";").split(";"):
        key, separator, value = chunk.strip().partition("=")
        key = key.strip()
        if separator and key:
            pairs.append((key, value.strip()))
    return pairs


def _flag(variable: str, value) -> list[str]:
    """Return the arguments that set one Tesseract config variable."""
    return ["-c", f"{variable}={value}"]


def _output_format_flags(options: OcrOptions) -> list[str]:
    # Output formats are requested through -c tessedit_create_* flags, not through positional configfile names
    # ("txt tsv pdf"). Those named configfiles live under <tessdata-dir>/configs/, which does not exist in a custom
    # --tessdata-dir holding only downloaded .traineddata files, and Tesseract would then silently skip the requested
    # formats.
    flags = _flag("tessedit_create_txt", 1)
    if options.want_confidence:
        flags += _flag("tessedit_create_tsv", 1)
    if options.want_pdf:
        flags += _flag("tessedit_create_pdf", 1)
    return flags


def _tuning_flags(options: OcrOptions) -> list[str]:
    flags: list[str] = []
    if options.preserve_interword_spaces:
        flags += _flag("preserve_interword_spaces", 1)
    for variable in TESSERACT_TOGGLE_VARIABLES:
        if getattr(options, variable):
            flags += _flag(variable, 1)
    if options.edges_max_children_per_outline is not None:
        flags += _flag("edges_max_children_per_outline", options.edges_max_children_per_outline)
    return flags


def _custom_param_flags(options: OcrOptions) -> list[str]:
    flags: list[str] = []
    for variable, value in parse_custom_params(options.custom_params):
        flags += _flag(variable, value)
    return flags


def build_command(image_path: str, output_base: str, lang: str, psm: int, options: OcrOptions) -> list[str]:
    """Return the full tesseract command for one image.

    Custom parameters come last on purpose: a value typed there for a variable that also has its own toggle (e.g.
    "chop_enable=0" to force it off, which the toggle alone cannot express) wins, because Tesseract uses the last -c
    value it sees.
    """
    command = [
        program.program(), image_path, output_base,
        "-l", lang,
        "--psm", str(psm),
        "--oem", str(normalize_oem(options.oem)),
    ]
    if options.tessdata_dir:
        command += ["--tessdata-dir", options.tessdata_dir]
    return (
        command
        + _output_format_flags(options)
        + _tuning_flags(options)
        + _custom_param_flags(options)
    )
