# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract/languages.py — Which OCR languages are available, and how
they are named in the UI.
"""
from __future__ import annotations

import subprocess

from providers import tessdata_manager
from providers.engine_settings import SYSTEM_LANG_SOURCE
from providers.tesseract import program
from providers.tesseract.install import is_installed
from providers.tesseract.lang_names import LANG_COMBOS, LANG_NAMES

DEFAULT_LANG = "ara+eng"

_LIST_LANGS_TIMEOUT_S = 10


def lang_display_name(code: str) -> str:
    """Human-readable name for a language code or a "+"-joined compound code."""
    if "+" in code:
        return " + ".join(LANG_NAMES.get(part, part) for part in code.split("+"))
    return LANG_NAMES.get(code, code)


def available_langs() -> list[str]:
    """Language packs installed on this machine (via the OS package manager)."""
    if not is_installed():
        return []
    try:
        result = subprocess.run(
            [program.program(), "--list-langs"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_LIST_LANGS_TIMEOUT_S, check=False,
            **program.quiet_window_options(),
        )
    except Exception:
        return []
    lines = (result.stdout + result.stderr).splitlines()
    # The first line is a header ("List of available tessdata...") — skip it.
    # "osd" and "equ" are real .traineddata files Tesseract lists, but they
    # are not usable OCR languages and would show up as confusing raw entries.
    return [
        name for name in (line.strip() for line in lines)
        if name and "List" not in name and name not in tessdata_manager.NON_LANGUAGE_CODES
    ]


def available_langs_for_source(source: str) -> list[str]:
    """
    Language codes available from a language *source*: "system" (installed
    via the OS package manager) or a tessdata_manager quality tier
    ("fast" / "standard" / "best") downloaded in-app without sudo.
    """
    if source == SYSTEM_LANG_SOURCE:
        return available_langs()
    return tessdata_manager.list_downloaded(source)


def build_lang_options(available: list[str]) -> list[tuple[str, str]]:
    """
    Ordered (code, display_name) pairs for the language pickers:
      1. Common compound combinations — only if all component packs are installed.
      2. Every other installed pack, sorted by display name.
    Each code appears at most once.
    """
    available_set = set(available)
    options = [
        (code, name) for code, name in LANG_COMBOS
        if all(part in available_set for part in code.split("+"))
    ]
    combo_codes = {code for code, _name in options}
    singles = sorted(
        ((lang, lang_display_name(lang)) for lang in available if lang not in combo_codes),
        key=lambda pair: pair[1].lower(),
    )
    return options + singles
