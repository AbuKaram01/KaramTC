# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""In-app downloader for Tesseract language data.

Lets the user fetch official ".traineddata" files directly from Tesseract's own GitHub data repositories, at one of
three quality tiers, without touching the system package manager: no sudo/root and no restart are required. Downloaded
files live under the app's own data directory and are used through Tesseract's --tessdata-dir flag, completely
independent from any system-installed tesseract-ocr-<lang> packages.

Quality tiers (these mirror Tesseract's three official data repositories):

  fast     - smallest and fastest, lower accuracy.
  standard - Tesseract's traditional default balance of speed and accuracy.
  best     - LSTM models trained for maximum accuracy; slower and larger.

This module has no GTK dependency and needs internet access only for the download() call itself; nothing else in the
app needs a network connection.

Note:
    osd.traineddata is not an OCR language. Tesseract loads it for orientation and script detection (PSM 1 and 12),
    and it is NOT bundled with any language pack: with a custom --tessdata-dir it has to be downloaded separately.
    It is handled by the same download() and delete() functions, but is kept out of list_downloaded() so that it never
    appears in a language picker.
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

# One URL template per quality tier; "%s" is the language code.
_DOWNLOAD_URLS = {
    "fast":     "https://github.com/tesseract-ocr/tessdata_fast/raw/refs/heads/main/%s.traineddata",
    "standard": "https://github.com/tesseract-ocr/tessdata/raw/refs/heads/main/%s.traineddata",
    "best":     "https://github.com/tesseract-ocr/tessdata_best/raw/refs/heads/main/%s.traineddata",
}

# The tiers in display order, as (id, display name) pairs for UI lists.
QUALITY_TIERS: list[tuple[str, str]] = [
    ("fast",     "Fast — smaller and quicker, lower accuracy"),
    ("standard", "Standard — Tesseract's default balance"),
    ("best",     "Best — most accurate, larger and slower"),
]

# Support files that live next to the language packs but are not OCR languages. They are never offered in language
# pickers (see list_downloaded).
OSD_CODE = "osd"
NON_LANGUAGE_CODES = frozenset({OSD_CODE, "equ"})

# Guards against the same (quality, code) being downloaded twice at once, e.g. with two OCR Settings dialogs open at
# the same time (one per tab, or one left open and reopened). Each dialog is unaware of the other's in-flight download,
# and both would write to the same ".part" file. Each dialog already disables its own download buttons while its own
# download runs, but that alone cannot see a download started from a different dialog instance. This lock is the single
# source of truth that makes a second concurrent attempt for the same file fail cleanly instead of corrupting the
# partial download.
_download_lock = threading.Lock()
_downloading: set[tuple[str, str]] = set()

# A .traineddata file smaller than this is almost certainly a truncated connection or a GitHub error page, not real
# model data: even the smallest real Tesseract language packs are several hundred KB.
_MIN_VALID_SIZE = 20_000


def _data_root() -> str:
    """Return the folder that holds one sub-folder of downloaded packs per quality tier."""
    return os.path.join(user_data_dir(), "tessdata")


# Tesseract language/script codes: letters, digits and underscores ("eng", "chi_sim_vert", "srp_latn"). Anything else
# (slashes, dots, "%") is refused before it can reach a file path or a URL.
_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,40}$")


def _valid_code(code) -> bool:
    """Return True if *code* is a well-formed language or script code (see _CODE_RE)."""
    return isinstance(code, str) and bool(_CODE_RE.match(code))


def local_tessdata_dir(quality: str) -> str:
    """Return the folder holding the downloaded packs for *quality*, creating it if possible.

    Raises:
        ValueError: *quality* is not one of the tiers in QUALITY_TIERS.
    """
    if quality not in _DOWNLOAD_URLS:
        raise ValueError(f"Unknown OCR quality tier: {quality!r}")
    path = os.path.join(_data_root(), quality)
    # With a read-only or missing data directory the folder simply stays empty (nothing downloaded); saving a download
    # reports the problem itself.
    with contextlib.suppress(OSError):
        os.makedirs(path, exist_ok=True)
    return path


def _model_path(quality: str, code: str) -> str:
    """Return the path of the .traineddata file for *code* in *quality*, after validating *code*."""
    if not _valid_code(code):
        raise ValueError(f"Invalid language code: {code!r}")
    return os.path.join(local_tessdata_dir(quality), f"{code}.traineddata")


def is_downloaded(quality: str, code: str) -> bool:
    """Return True if *code* has a plausibly valid downloaded pack for *quality*."""
    try:
        path = _model_path(quality, code)
        return os.path.isfile(path) and os.path.getsize(path) >= _MIN_VALID_SIZE
    except (ValueError, OSError):
        return False


def has_osd(quality: str) -> bool:
    """Return True if osd.traineddata (orientation and script detection) is downloaded for *quality*."""
    return is_downloaded(quality, OSD_CODE)


def list_downloaded(quality: str) -> list[str]:
    """Return the sorted language codes already downloaded for *quality*.

    Support files such as osd are excluded because they are not selectable languages.
    """
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
    """Remove a downloaded language pack; do nothing if it is absent."""
    with contextlib.suppress(OSError, ValueError):
        os.remove(_model_path(quality, code))


def download(quality: str, code: str, progress_cb=None, cancel_event=None) -> None:
    """Download one language's .traineddata file for the given quality tier.

    A failed download removes any partial file it leaves behind, so that a later retry never sees a corrupt
    half-downloaded model sitting there looking valid.

    Args:
        quality: The quality tier (an id from QUALITY_TIERS).
        code: The language or script code, e.g. "eng".
        progress_cb: Optional callable(percent: int | None). None means "downloading, but total size unknown" (no
            Content-Length header); the caller should show an indeterminate spinner in that case.
        cancel_event: Optional threading.Event, polled between chunks.

    Raises:
        RuntimeError: Bad quality tier or language code, a download of the same file already in progress, a network
            error, or a cancelled download.
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
# How much of the start of a download is inspected to tell an HTML error page from model data.
_HTML_SNIFF_BYTES = 512


def _stream_to_file(url: str, part_path: str, progress_cb, cancel_event) -> int | None:
    """Download *url* into *part_path* and return the expected size (None if the server did not say)."""
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
    """Return a readable RuntimeError for a known failure, or None if *exc* should propagate as is."""
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return RuntimeError(
                f"No {quality!r} language data found for code '{code}' "
                "— double-check the language code"
            )
        return RuntimeError(f"Download failed: HTTP {exc.code}")
    if isinstance(exc, urllib.error.URLError):
        return RuntimeError(f"Download failed: {exc.reason}")
    # For example IncompleteRead: the connection dropped in the middle of the file.
    if isinstance(exc, http.client.HTTPException):
        return RuntimeError("The connection was interrupted during the download — try again")
    if isinstance(exc, TimeoutError):
        return RuntimeError("The connection timed out during the download — try again")
    # The file cannot be written: disk full, read-only, no permission, ...
    if isinstance(exc, OSError):
        return RuntimeError(f"Could not save the language data: {exc.strerror or exc}")
    return None


def _problem_with_download(part_path: str, expected_size: int | None) -> str | None:
    """Return why the downloaded file cannot be trusted, or None if it looks like real model data."""
    size = os.path.getsize(part_path)
    if size < _MIN_VALID_SIZE:
        return "Downloaded file looks incomplete or corrupt — try again"
    if expected_size is not None and size != expected_size:
        return "The download was cut short — try again"
    with open(part_path, "rb") as part_file:
        # A leading "<" means an HTML page, not model data.
        if part_file.read(_HTML_SNIFF_BYTES).lstrip()[:1] == b"<":
            return "The server returned a web page instead of language data — try again later"
    return None


def _do_download(quality: str, code: str, progress_cb, cancel_event) -> None:
    """Fetch the file into a ".part" file, check it, then move it into place.

    The final name only ever holds a complete, checked download.
    """
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
    """Remove a partial download; ignore a file that is already gone or cannot be removed."""
    with contextlib.suppress(OSError):
        os.remove(part_path)
