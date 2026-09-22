# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
ui/ocr_settings/osd_offer.py — Offers to download the orientation data (osd).
"""
from __future__ import annotations

import threading

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw, GLib

from providers import tessdata_manager
from providers.engine_settings import SYSTEM_LANG_SOURCE
from providers.tesseract import psm_needs_osd

_START_TOAST_TIMEOUT_S = 3
_ERROR_TOAST_TIMEOUT_S = 5


class OsdOffer:
    """
    PSM 1 and 12 use orientation/script detection, which needs osd.traineddata
    — a file no language pack contains. With a downloaded language source it
    is absent unless fetched separately, so offer to fetch it as soon as such
    a mode is selected (or the source changes to one that lacks it). The
    System source is left alone: its packages normally include osd, and OCR
    reports a clear error if not.
    """

    def __init__(self, host: Adw.PreferencesDialog):
        self._host = host
        self._download_active = False

    def offer_if_needed(self, psm: int, psm_label: str, source: str) -> None:
        if (
            not psm_needs_osd(psm)
            or source == SYSTEM_LANG_SOURCE
            or tessdata_manager.has_osd(source)
            or self._download_active
        ):
            return
        dialog = Adw.AlertDialog(
            heading="Orientation data needed",
            body=(
                f"\u201c{psm_label}\u201d uses orientation and script detection, which needs a "
                f"separate data file (about 10 MB) that isn\u2019t part of any language pack.\n\n"
                f"Download it for the {source.capitalize()} source now? Without it, OCR in this "
                "mode will report an error until you download it or choose another mode."
            ),
        )
        dialog.add_response("later", "Not Now")
        dialog.add_response("download", "Download")
        dialog.set_response_appearance("download", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("download")
        dialog.set_close_response("later")
        dialog.connect("response", lambda _dialog, response: self._on_response(response, source))
        dialog.present(self._host)

    def _on_response(self, response: str, source: str) -> None:
        if response != "download" or self._download_active:
            return
        self._download_active = True
        self._toast("Downloading orientation data\u2026", _START_TOAST_TIMEOUT_S)
        threading.Thread(target=self._download, args=(source,), daemon=True).start()

    def _download(self, source: str) -> None:
        try:
            tessdata_manager.download(source, tessdata_manager.OSD_CODE)
            GLib.idle_add(self._on_download_done, None)
        except Exception as exc:
            GLib.idle_add(self._on_download_done, str(exc))

    def _on_download_done(self, error: str | None) -> bool:
        self._download_active = False
        if error:
            self._toast(f"Could not download orientation data: {error}", _ERROR_TOAST_TIMEOUT_S)
        else:
            self._toast("Orientation data downloaded \u2713", _START_TOAST_TIMEOUT_S)
        return GLib.SOURCE_REMOVE

    def _toast(self, message: str, timeout: int) -> None:
        toast = Adw.Toast(title=message, timeout=timeout)
        toast.set_use_markup(False)
        self._host.add_toast(toast)
