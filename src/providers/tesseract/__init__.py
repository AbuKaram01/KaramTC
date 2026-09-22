# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tesseract — Tesseract OCR provider (local, no internet required).

The registry requires `ocr()`; the rest is the public surface the UI uses
for language lists, install hints and engine settings.

Installation:
  Ubuntu / Debian : sudo apt install tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng
  Fedora          : sudo dnf install tesseract tesseract-langpack-ara
  Arch            : sudo pacman -S tesseract tesseract-data-ara tesseract-data-eng
  macOS           : brew install tesseract tesseract-lang
"""
from providers.tesseract.cpu import (
    CPU_USAGE_OPTIONS, DEFAULT_CPU_USAGE, cpu_cores, normalize_cpu_usage, threads_for_usage,
)
from providers.tesseract.engine import ocr
from providers.tesseract.install import install_hint, is_installed, osd_install_hint
from providers.tesseract.lang_names import LANG_COMBOS, LANG_NAMES
from providers.tesseract.languages import (
    DEFAULT_LANG, available_langs, available_langs_for_source,
    build_lang_options, lang_display_name,
)
from providers.tesseract.options import (
    OEM_OPTIONS, PSM_NEEDS_OSD, PSM_OPTIONS, normalize_oem, normalize_psm, psm_index, psm_needs_osd,
)
from providers.tesseract.process import terminate_active_processes

__all__ = [
    "CPU_USAGE_OPTIONS", "DEFAULT_CPU_USAGE", "DEFAULT_LANG", "LANG_COMBOS", "LANG_NAMES",
    "OEM_OPTIONS", "PSM_NEEDS_OSD", "PSM_OPTIONS",
    "available_langs", "available_langs_for_source", "build_lang_options", "cpu_cores",
    "install_hint", "is_installed", "lang_display_name", "normalize_cpu_usage",
    "normalize_oem", "normalize_psm", "ocr", "osd_install_hint", "psm_index",
    "psm_needs_osd", "terminate_active_processes", "threads_for_usage",
]
