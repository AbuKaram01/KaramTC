# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/model_store.py — Downloads and keeps the Whisper models (large-v3 turbo and large-v3).

Each model is the CTranslate2 conversion published on Hugging Face (MIT
licence) and lives in its own folder, so both can be kept side by side. The
download is resumable — an interrupted or cancelled one continues where it
stopped — and every file is checked against the size and SHA-256 the
repository reports, so a truncated or corrupt model is never used.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from config import user_data_dir
from core.media.errors import DownloadCancelledError

MODEL_REVISION = "main"
HF_BASE_URL = "https://huggingface.co"

# The files faster-whisper needs. The big one goes last, so a model folder
# without a manifest never looks complete while it is still downloading.
REQUIRED_FILES = ("config.json", "preprocessor_config.json", "tokenizer.json", "vocabulary.json", "model.bin")
_MANIFEST_NAME = "manifest.json"
_PART_SUFFIX = ".part"

_CHUNK_SIZE = 1024 * 1024
_REQUEST_TIMEOUT_S = 30

ProgressCallback = Callable[[int, int, str], None]      # (bytes done, bytes total, what is happening)


@dataclass(frozen=True)
class RemoteFile:
    name: str
    size: int
    sha256: str | None      # only large (LFS) files carry one


@dataclass(frozen=True)
class WhisperModel:
    """A Whisper model KaramTC can download."""
    id: str                 # what is saved in settings.json
    label: str
    repo: str               # the Hugging Face repository
    folder: str             # inside models_root(); the path is built from this, never from the saved id
    size_text: str
    summary: str            # finishes the sentence "<label> ..." on the Speech Settings page
    recommended: bool = False

    @property
    def display_label(self) -> str:
        """The label as shown in the lists: the recommended model says so."""
        return f"{self.label} (Recommended)" if self.recommended else self.label


MODELS = (
    WhisperModel(
        "large-v3-turbo", "Whisper large-v3 turbo", "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "whisper-large-v3-turbo", "about 1.6 GB",
        "recognises about 100 languages and runs fast on a CPU or a GPU.",
        recommended=True,
    ),
    WhisperModel(
        "large-v3", "Whisper large-v3", "Systran/faster-whisper-large-v3",
        "whisper-large-v3", "about 3.1 GB",
        "is the full-size model: it recognises about 100 languages, but is about twice as large "
        "and noticeably slower than turbo.",
    ),
)
DEFAULT_MODEL_ID = "large-v3-turbo"


def get_model(model_id: str | None = None) -> WhisperModel:
    """The catalog entry for *model_id*; the default model for None or an id the catalog doesn't know."""
    for model in MODELS:
        if model.id == model_id:
            return model
    return next(model for model in MODELS if model.id == DEFAULT_MODEL_ID)


def models_root() -> str:
    return os.path.join(user_data_dir(), "models")


def managed_model_dir(model_id: str | None = None) -> str:
    return os.path.join(models_root(), get_model(model_id).folder)


# ── What is on disk ─────────────────────────────────────────────────

def _read_manifest(model_dir: str) -> dict | None:
    try:
        with open(os.path.join(model_dir, _MANIFEST_NAME), encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) and isinstance(manifest.get("files"), dict) else None


def is_downloaded(model_dir: str | None = None, model_id: str | None = None) -> bool:
    """True if every required file is present at exactly the size recorded when the download finished.

    Looks in *model_dir*, or in the managed folder of *model_id* (the default model if neither is given)."""
    model_dir = model_dir or managed_model_dir(model_id)
    manifest = _read_manifest(model_dir)
    if manifest is None:
        return False
    for name in REQUIRED_FILES:
        try:
            if os.path.getsize(os.path.join(model_dir, name)) != manifest["files"].get(name):
                return False
        except OSError:
            return False
    return True


def has_partial_download(model_dir: str | None = None, model_id: str | None = None) -> bool:
    model_dir = model_dir or managed_model_dir(model_id)
    return any(os.path.exists(os.path.join(model_dir, name + _PART_SUFFIX)) for name in REQUIRED_FILES)


def delete(model_dir: str | None = None, model_id: str | None = None) -> None:
    """Removes the downloaded model (and any partial download); other models are left alone."""
    shutil.rmtree(model_dir or managed_model_dir(model_id), ignore_errors=True)


# ── Asking the server ───────────────────────────────────────────────

def _open(request: urllib.request.Request):
    return urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_S)  # noqa: S310 — https URL built from constants


def list_remote_files(base_url: str = HF_BASE_URL, model_id: str | None = None) -> dict[str, RemoteFile]:
    """Size and checksum of every required file, as the repository reports them."""
    url = f"{base_url}/api/models/{get_model(model_id).repo}/tree/{MODEL_REVISION}"
    with _open(urllib.request.Request(url, headers={"Accept": "application/json"})) as response:
        entries = json.load(response)
    found = {}
    for entry in entries:
        if entry.get("type") == "file" and entry.get("path") in REQUIRED_FILES:
            lfs = entry.get("lfs") or {}
            found[entry["path"]] = RemoteFile(entry["path"], int(lfs.get("size", entry["size"])), lfs.get("oid"))
    missing = [name for name in REQUIRED_FILES if name not in found]
    if missing:
        raise RuntimeError(f"The model repository does not contain: {', '.join(missing)}")
    return found


def _friendly_error(error: Exception) -> Exception:
    """A readable message for a failed download; the partial file is kept so Download continues it."""
    if isinstance(error, urllib.error.HTTPError):
        return RuntimeError(f"The download server answered with an error (HTTP {error.code}) — try again later")
    if isinstance(error, urllib.error.URLError):
        return RuntimeError(f"Could not reach the download server: {error.reason}")
    if isinstance(error, (http.client.HTTPException, TimeoutError, ConnectionError)):
        return RuntimeError("The connection was interrupted — press Download again to continue where it stopped")
    if isinstance(error, OSError):
        return RuntimeError(f"Could not save the model: {error.strerror or error}")
    return error


# ── Downloading ─────────────────────────────────────────────────────

def _raise_if_cancelled(cancel_event) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise DownloadCancelledError()


def _sha256_of(path: str, cancel_event) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as checked_file:
        while chunk := checked_file.read(_CHUNK_SIZE):
            _raise_if_cancelled(cancel_event)
            digest.update(chunk)
    return digest.hexdigest()


class _Download:
    """One download of the whole model into a folder."""

    def __init__(self, model: WhisperModel, model_dir: str, base_url: str, progress: ProgressCallback, cancel_event):
        self._model = model
        self._model_dir = model_dir
        self._base_url = base_url
        self._progress = progress
        self._cancel_event = cancel_event
        self._remote: dict[str, RemoteFile] = {}
        self._total = 0

    def run(self) -> None:
        os.makedirs(self._model_dir, exist_ok=True)
        self._remote = list_remote_files(self._base_url, self._model.id)
        self._total = sum(self._remote[name].size for name in REQUIRED_FILES)
        done = 0
        for name in REQUIRED_FILES:
            _raise_if_cancelled(self._cancel_event)
            self._fetch(self._remote[name], done)
            done += self._remote[name].size
        self._write_manifest()
        self._progress(self._total, self._total, "Done")

    def _fetch(self, remote: RemoteFile, done_before: int) -> None:
        final_path = os.path.join(self._model_dir, remote.name)
        if os.path.isfile(final_path) and os.path.getsize(final_path) == remote.size:
            self._progress(done_before + remote.size, self._total, remote.name)
            return
        part_path = final_path + _PART_SUFFIX
        start = os.path.getsize(part_path) if os.path.exists(part_path) else 0
        if start > remote.size:
            os.remove(part_path)
            start = 0
        if start < remote.size:
            self._receive(remote, part_path, start, done_before)
        self._verify(remote, part_path, done_before)
        os.replace(part_path, final_path)

    def _receive(self, remote: RemoteFile, part_path: str, start: int, done_before: int) -> None:
        url = f"{self._base_url}/{self._model.repo}/resolve/{MODEL_REVISION}/{remote.name}"
        headers = {"Range": f"bytes={start}-"} if start else {}
        with _open(urllib.request.Request(url, headers=headers)) as response:
            # A server that ignores the Range header answers 200 with the whole file.
            done = start if response.status == 206 else 0
            with open(part_path, "ab" if done else "wb") as part_file:
                while chunk := response.read(_CHUNK_SIZE):
                    _raise_if_cancelled(self._cancel_event)
                    part_file.write(chunk)
                    done += len(chunk)
                    self._progress(done_before + done, self._total, remote.name)

    def _verify(self, remote: RemoteFile, part_path: str, done_before: int) -> None:
        if os.path.getsize(part_path) != remote.size:
            raise RuntimeError(f"{remote.name} was cut short — press Download again to continue")
        if not remote.sha256:
            return
        self._progress(done_before + remote.size, self._total, f"Verifying {remote.name}…")
        if _sha256_of(part_path, self._cancel_event) != remote.sha256:
            os.remove(part_path)
            raise RuntimeError(f"{remote.name} did not download correctly (checksum mismatch) — try again")

    def _write_manifest(self) -> None:
        manifest = {
            "repo": self._model.repo, "revision": MODEL_REVISION,
            "files": {name: self._remote[name].size for name in REQUIRED_FILES},
        }
        temporary = os.path.join(self._model_dir, _MANIFEST_NAME + _PART_SUFFIX)
        with open(temporary, "w", encoding="utf-8") as manifest_file:
            json.dump(manifest, manifest_file, indent=2)
        os.replace(temporary, os.path.join(self._model_dir, _MANIFEST_NAME))


def download(
    progress: ProgressCallback | None = None,
    cancel_event=None,
    base_url: str = HF_BASE_URL,
    model_dir: str | None = None,
    model_id: str | None = None,
) -> None:
    """
    Downloads a model into *model_dir* (the managed folder of *model_id* by default).

    :param progress: called as progress(bytes_done, bytes_total, what).
    :param model_id: which model from MODELS; the default (turbo) if not given.
    :raises DownloadCancelledError: if *cancel_event* was set; what was fetched
        so far is kept and the next call continues from it.
    """
    try:
        model = get_model(model_id)
        _Download(
            model, model_dir or managed_model_dir(model.id), base_url,
            progress or (lambda _done, _total, _what: None), cancel_event,
        ).run()
    except (DownloadCancelledError, RuntimeError):
        raise
    except Exception as exc:
        raise _friendly_error(exc) from exc
