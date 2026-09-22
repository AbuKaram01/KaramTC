# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/saved_settings.py — The user's saved choices, read into domain objects.

Defines every settings.json key the UI uses, so no key is spelled twice, and
the one place that turns saved OCR Settings into engine settings — both tabs
read the exact same settings the same way.
"""
from __future__ import annotations

import settings as app_settings
from core.media import DEVICE_AUTO, DEVICES, MODEL_SOURCES, SOURCE_CUSTOM, SOURCE_MANAGED, EngineSettings
from core.media import model_store
from core.media.hardware import default_cpu_threads
from core.media.model_location import ModelStatus, model_status
from providers import tessdata_manager
from providers.engine_settings import EDGES_VARIABLE, SYSTEM_LANG_SOURCE, OcrEngineSettings
from providers.ocr_types import DEFAULT_OEM, DEFAULT_PSM, TESSERACT_TOGGLE_VARIABLES, OcrOptions
from providers.tesseract import DEFAULT_CPU_USAGE, threads_for_usage

# OCR Settings (shared by both tabs)
OCR_LANG_SOURCE = "ocr_lang_source"
OCR_CPU_USAGE = "ocr_cpu_usage"
OCR_OEM = "ocr_oem"
OCR_PSM = "ocr_psm"
OCR_PRESERVE_SPACES = "ocr_preserve_spaces"
OCR_CUSTOM_PARAMS = "ocr_custom_params"
OCR_EDGES_ENABLED = "ocr_edges_max_children_enabled"
OCR_EDGES_VALUE = "ocr_edges_max_children_value"
PDF_IMAGE_DPI = "pdf_image_dpi"
PDF_JPEG_QUALITY = "pdf_jpeg_quality"

# Remembered between sessions
LAST_OCR_LANG = "last_ocr_lang"
OCR_OUTPUT_FORMAT = "ocr_output_format"
PDF_PAGE_NUMBERS = "pdf_page_numbers"
PDF_ENHANCE_CONTRAST = "pdf_enhance_contrast"
PDF_IMAGE_MODE = "pdf_image_mode"
PDF_OUTPUT_DIR = "pdf_output_dir"

# Speech Settings and the Audio/Video tab
SPEECH_MODEL_SOURCE = "speech_model_source"
SPEECH_MODEL_CHOICE = "speech_model_choice"      # which downloadable model (core.media.model_store.MODELS)
SPEECH_MODEL_DIR = "speech_model_dir"
SPEECH_DEVICE = "speech_device"
SPEECH_THREADS = "speech_cpu_threads"
SPEECH_RESUME = "speech_resume"
MEDIA_LANGUAGE = "media_language"               # "" means detect it
MEDIA_OUTPUT_FORMAT = "media_output_format"
MEDIA_TEXT_LAYOUT = "media_text_layout"
MEDIA_TIMESTAMPS = "media_timestamps"
MEDIA_OUTPUT_DIR = "media_output_dir"

# The window and its tabs, remembered between sessions
WINDOW_WIDTH = "window_width"                   # the normal (not maximized) size
WINDOW_HEIGHT = "window_height"
WINDOW_MAXIMIZED = "window_maximized"
LAST_TAB = "last_tab"

WINDOW_DEFAULT_SIZE = (700, 620)
WINDOW_MIN_SIZE = (400, 540)                    # the smallest the window can be made
WINDOW_MAX_SIZE = (16384, 16384)                # a damaged file can't ask for an absurd window

SPEECH_THREADS_RANGE = (1, 64)

EDGES_DEFAULT_VALUE = 40
EDGES_VALUE_RANGE = (1, 1000)   # a Tesseract tuning value, normally 1-100; clamped so a damaged setting can't pass nonsense


def toggle_setting_key(variable: str) -> str:
    """The settings key of a Tesseract toggle variable (e.g. "ocr_chop_enable")."""
    return f"ocr_{variable}"


def valid_lang_source() -> str:
    """The saved language-data source ("system" or a quality tier), or "system"
    if the stored value isn't one — it is used to build folder names, so an
    arbitrary string from a damaged settings file must never get through."""
    source = app_settings.get(OCR_LANG_SOURCE, SYSTEM_LANG_SOURCE)
    valid_sources = (SYSTEM_LANG_SOURCE, *(tier for tier, _label in tessdata_manager.QUALITY_TIERS))
    return source if source in valid_sources else SYSTEM_LANG_SOURCE


def cpu_threads_setting() -> int | None:
    """Thread limit for the saved "CPU usage" choice (None = leave Tesseract alone)."""
    return threads_for_usage(app_settings.get(OCR_CPU_USAGE, DEFAULT_CPU_USAGE))


def read_tess_extra_settings() -> dict:
    """The named Tesseract toggles from the saved OCR Settings, in the shape
    OcrEngineSettings.extra_variables expects."""
    extra = {
        variable: app_settings.get(toggle_setting_key(variable), False)
        for variable in TESSERACT_TOGGLE_VARIABLES
    }
    if app_settings.get(OCR_EDGES_ENABLED, False):
        low, high = EDGES_VALUE_RANGE
        extra[EDGES_VARIABLE] = max(low, min(high, app_settings.get(OCR_EDGES_VALUE, EDGES_DEFAULT_VALUE)))
    return extra


def read_engine_settings() -> OcrEngineSettings:
    return OcrEngineSettings(
        oem=app_settings.get(OCR_OEM, DEFAULT_OEM),
        psm=app_settings.get(OCR_PSM, DEFAULT_PSM),
        preserve_interword_spaces=app_settings.get(OCR_PRESERVE_SPACES, False),
        custom_params=app_settings.get(OCR_CUSTOM_PARAMS, ""),
        lang_source=valid_lang_source(),
        extra_variables=read_tess_extra_settings(),
    )


def build_ocr_options(want_pdf: bool = False, want_confidence: bool = True) -> OcrOptions:
    """OcrOptions from the saved OCR Settings — used by the Image tab, which
    has no per-job settings of its own (unlike the PDF tab's resumable jobs)."""
    return read_engine_settings().to_ocr_options(
        want_pdf=want_pdf, want_confidence=want_confidence, threads=cpu_threads_setting(),
    )


def speech_model_source() -> str:
    """The saved speech-model source, or the managed download if the stored value isn't a known one."""
    source = app_settings.get(SPEECH_MODEL_SOURCE, SOURCE_MANAGED)
    return source if source in MODEL_SOURCES else SOURCE_MANAGED


def speech_model_id() -> str:
    """The saved downloadable model's id, or the default (recommended) one if the stored value isn't in the
    catalog — a damaged settings file must never pick a model that doesn't exist."""
    choice = app_settings.get(SPEECH_MODEL_CHOICE, model_store.DEFAULT_MODEL_ID)
    known = any(choice == model.id for model in model_store.MODELS)
    return choice if known else model_store.DEFAULT_MODEL_ID


def speech_device() -> str:
    device = app_settings.get(SPEECH_DEVICE, DEVICE_AUTO)
    return device if device in DEVICES else DEVICE_AUTO


def speech_threads() -> int:
    low, high = SPEECH_THREADS_RANGE
    return max(low, min(high, app_settings.get(SPEECH_THREADS, default_cpu_threads())))


def read_speech_engine_settings() -> EngineSettings:
    """How the speech model is loaded, from the saved Speech Settings."""
    if speech_model_source() == SOURCE_CUSTOM:
        model_dir = app_settings.get(SPEECH_MODEL_DIR, "")
    else:
        model_dir = model_store.managed_model_dir(speech_model_id())
    return EngineSettings(model_dir, speech_device(), speech_threads())


def speech_model_status() -> ModelStatus:
    """Whether the chosen speech model can be used right now, and a sentence saying why not."""
    return model_status(speech_model_source(), app_settings.get(SPEECH_MODEL_DIR, ""), speech_model_id())


def speech_resume_enabled() -> bool:
    return bool(app_settings.get(SPEECH_RESUME, False))


def window_size() -> tuple[int, int]:
    """The saved window size (width, height), kept within what a window can sensibly be."""
    width, height = (
        max(low, min(high, app_settings.get(key, default)))
        for key, default, low, high in (
            (WINDOW_WIDTH, WINDOW_DEFAULT_SIZE[0], WINDOW_MIN_SIZE[0], WINDOW_MAX_SIZE[0]),
            (WINDOW_HEIGHT, WINDOW_DEFAULT_SIZE[1], WINDOW_MIN_SIZE[1], WINDOW_MAX_SIZE[1]),
        )
    )
    return width, height


def window_maximized() -> bool:
    return bool(app_settings.get(WINDOW_MAXIMIZED, False))
