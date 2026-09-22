# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
providers/tessdata_manager.py — In-app Tesseract language-data downloader.

Lets the user fetch official Tesseract ".traineddata" files directly from
Tesseract's own GitHub data repositories, at one of three quality tiers,
without touching the system package manager — no sudo/root and no restart
required. Downloaded files live under the app's own data directory and are
used via Tesseract's --tessdata-dir flag, completely independent from any
system-installed tesseract-ocr-<lang> packages.

Quality tiers (mirrors Tesseract's own three official data repositories):
  fast     — smallest / fastest, lower accuracy
  standard — Tesseract's traditional default balance of speed and accuracy
  best     — LSTM models trained for maximum accuracy; slower & larger

This module has no GTK dependency and requires internet access only for the
download() call itself — nothing else in the app needs a network connection.

Public API:
  QUALITY_TIERS                 : ordered [(id, display_name), ...] for UI lists.
  local_tessdata_dir(quality)   : path to the folder holding downloaded packs.
  list_downloaded(quality)      : language codes already downloaded for a tier.
  is_downloaded(quality, code)  : True if a given language is downloaded.
  has_osd(quality)              : True if the orientation/script data is present.
  download(quality, code, ...)  : fetches one .traineddata file.
  delete(quality, code)         : removes a downloaded .traineddata file.

Note on "osd": osd.traineddata is not an OCR language. Tesseract loads it for
orientation and script detection (PSM 1 and 12), and it is NOT bundled with
any language pack — with a custom --tessdata-dir it has to be downloaded
separately. It is handled by the same download()/delete() functions, but is
kept out of list_downloaded() so it never appears in a language picker.
"""
from __future__ import annotations

import contextlib
import http.client
import os
import re
import threading
import urllib.error
import urllib.request

from config import user_data_dir

_DOWNLOAD_URLS = {
    "fast":     "https://github.com/tesseract-ocr/tessdata_fast/raw/refs/heads/main/%s.traineddata",
    "standard": "https://github.com/tesseract-ocr/tessdata/raw/refs/heads/main/%s.traineddata",
    "best":     "https://github.com/tesseract-ocr/tessdata_best/raw/refs/heads/main/%s.traineddata",
}

QUALITY_TIERS: list[tuple[str, str]] = [
    ("fast",     "Fast — smaller and quicker, lower accuracy"),
    ("standard", "Standard — Tesseract's default balance"),
    ("best",     "Best — most accurate, larger and slower"),
]

# Support files that live next to the language packs but are not OCR
# languages. Never offered in language pickers (see list_downloaded).
OSD_CODE = "osd"
NON_LANGUAGE_CODES = frozenset({OSD_CODE, "equ"})

# Guards against the same (quality, code) being downloaded twice at once —
# e.g. two OCR Settings dialogs open at the same time (one per tab, or one
# left open and reopened), each unaware of the other's in-flight download,
# both writing to the same ".part" file. Each UI dialog already disables its
# own download buttons while ITS OWN download runs, but that alone can't see
# a download started from a different dialog instance — this lock is the
# actual, single source of truth that makes a second concurrent attempt for
# the same file fail cleanly instead of corrupting the partial download.
_download_lock = threading.Lock()
_downloading: set[tuple[str, str]] = set()

# A .traineddata file smaller than this is almost certainly a truncated
# connection or a GitHub error page, not real model data — even the smallest
# real Tesseract language packs are several hundred KB.
_MIN_VALID_SIZE = 20_000


def _data_root() -> str:
    return os.path.join(user_data_dir(), "tessdata")


# Tesseract language/script codes: letters, digits and underscores ("eng",
# "chi_sim_vert", "srp_latn"). Anything else — slashes, dots, "%" — is refused
# before it can reach a file path or a URL.
_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")


def _valid_code(code) -> bool:
    return isinstance(code, str) and bool(_CODE_RE.match(code))


def local_tessdata_dir(quality: str) -> str:
    """Returns (and tries to create) the folder holding downloaded packs for *quality*."""
    if quality not in _DOWNLOAD_URLS:
        raise ValueError(f"Unknown OCR quality tier: {quality!r}")
    path = os.path.join(_data_root(), quality)
    # Read-only or missing data directory: the folder simply stays empty
    # (nothing downloaded). Saving a download reports the problem itself.
    with contextlib.suppress(OSError):
        os.makedirs(path, exist_ok=True)
    return path


def _model_path(quality: str, code: str) -> str:
    if not _valid_code(code):
        raise ValueError(f"Invalid language code: {code!r}")
    return os.path.join(local_tessdata_dir(quality), f"{code}.traineddata")


def is_downloaded(quality: str, code: str) -> bool:
    """True if *code* has a plausibly-valid downloaded pack for *quality*."""
    try:
        path = _model_path(quality, code)
        return os.path.isfile(path) and os.path.getsize(path) >= _MIN_VALID_SIZE
    except (ValueError, OSError):
        return False


def has_osd(quality: str) -> bool:
    """True if osd.traineddata (orientation/script detection) is downloaded for *quality*."""
    return is_downloaded(quality, OSD_CODE)


def list_downloaded(quality: str) -> list[str]:
    """Returns the sorted list of OCR language codes downloaded for *quality*.
    Support files such as osd are excluded — they are not selectable languages."""
    codes = []
    try:
        folder = local_tessdata_dir(quality)
        for fname in os.listdir(folder):
            if fname.endswith(".traineddata"):
                code = fname[: -len(".traineddata")]
                if code in NON_LANGUAGE_CODES:
                    continue
                if is_downloaded(quality, code):
                    codes.append(code)
    except (OSError, ValueError):
        pass
    return sorted(codes)


def delete(quality: str, code: str) -> None:
    """Removes a downloaded language pack. Silently does nothing if absent."""
    with contextlib.suppress(OSError, ValueError):
        os.remove(_model_path(quality, code))


def download(quality: str, code: str, progress_cb=None, cancel_event=None) -> None:
    """
    Downloads one language's .traineddata file for the given quality tier.

    Raises RuntimeError on failure (bad language code, network error, or a
    cancelled download) and always removes any partial file it leaves behind,
    so a later retry never sees a corrupt half-downloaded model sitting there
    looking valid.

    :param progress_cb:  Optional callable(percent: int | None). None means
                         "downloading, but total size unknown" (no
                         Content-Length header) — the caller should show an
                         indeterminate spinner in that case.
    :param cancel_event: Optional threading.Event, polled between chunks.
    """
    if quality not in _DOWNLOAD_URLS:
        raise RuntimeError(f"Unknown OCR quality tier: {quality!r}")
    if not _valid_code(code):
        raise RuntimeError(f"Invalid language code: {code!r}")

    key = (quality, code)
    with _download_lock:
        if key in _downloading:
            raise RuntimeError(
                f"Already downloading {code!r} ({quality}) \u2014 please wait for it to finish"
            )
        _downloading.add(key)

    try:
        _do_download(quality, code, progress_cb, cancel_event)
    finally:
        with _download_lock:
            _downloading.discard(key)


_CHUNK_SIZE = 65536
_REQUEST_TIMEOUT_S = 30
_HTML_SNIFF_BYTES = 512


def _stream_to_file(url: str, part_path: str, progress_cb, cancel_event) -> int | None:
    """Downloads *url* into *part_path*; returns the expected size (None if the server didn't say)."""
    with urllib.request.urlopen(url, timeout=_REQUEST_TIMEOUT_S) as response:
        if response.status != 200:
            raise RuntimeError(f"Server returned HTTP {response.status}")
        length_header = response.getheader("Content-Length")
        expected_size = int(length_header) if length_header else None
        written = 0
        with open(part_path, "wb") as part_file:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("Cancelled by user")
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    return expected_size
                part_file.write(chunk)
                written += len(chunk)
                if progress_cb:
                    progress_cb(int(written * 100 / expected_size) if expected_size else None)


def _friendly_download_error(exc: Exception, quality: str, code: str) -> RuntimeError | None:
    """A readable RuntimeError for a known failure, or None if *exc* should propagate as is."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return RuntimeError(
                f"No {quality!r} language data found for code '{code}' "
                "— double-check the language code"
            )
        return RuntimeError(f"Download failed: HTTP {exc.code}")
    if isinstance(exc, urllib.error.URLError):
        return RuntimeError(f"Download failed: {exc.reason}")
    if isinstance(exc, http.client.HTTPException):      # e.g. IncompleteRead: connection dropped mid-file
        return RuntimeError("The connection was interrupted during the download — try again")
    if isinstance(exc, TimeoutError):
        return RuntimeError("The connection timed out during the download — try again")
    if isinstance(exc, OSError):                        # can't write the file: disk full, read-only, no permission…
        return RuntimeError(f"Could not save the language data: {exc.strerror or exc}")
    return None


def _problem_with_download(part_path: str, expected_size: int | None) -> str | None:
    """Why the downloaded file can't be trusted, or None if it looks like real model data."""
    size = os.path.getsize(part_path)
    if size < _MIN_VALID_SIZE:
        return "Downloaded file looks incomplete or corrupt — try again"
    if expected_size is not None and size != expected_size:
        return "The download was cut short — try again"
    with open(part_path, "rb") as part_file:
        if part_file.read(_HTML_SNIFF_BYTES).lstrip()[:1] == b"<":      # an HTML page, not model data
            return "The server returned a web page instead of language data — try again later"
    return None


def _do_download(quality: str, code: str, progress_cb, cancel_event) -> None:
    url = _DOWNLOAD_URLS[quality] % code
    final_path = _model_path(quality, code)
    part_path = final_path + ".part"

    try:
        expected_size = _stream_to_file(url, part_path, progress_cb, cancel_event)
    except Exception as exc:
        _cleanup_partial(part_path)
        friendly = _friendly_download_error(exc, quality, code)
        if friendly is None:
            raise
        raise friendly from exc

    problem = _problem_with_download(part_path, expected_size)
    if problem:
        _cleanup_partial(part_path)
        raise RuntimeError(problem)
    os.replace(part_path, final_path)


def _cleanup_partial(part_path: str) -> None:
    with contextlib.suppress(OSError):
        os.remove(part_path)
