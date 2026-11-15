# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Persistent user preferences, stored as JSON in the XDG config directory.

The file is ~/.config/<APP_ID>/settings.json (see config.APP_ID). Every read goes back to the file, so the module
keeps no in-memory copy of the settings; the exception is values that cannot be written, which are held in memory for
the rest of the session.

Public API:
    load() -> dict: All saved settings (an empty dict if there are none).
    save(data): Overwrite the settings file atomically.
    get(key, default): Read one key from disk.
    set(key, value): Write one key to disk, merging with the existing data.
    remove(key): Delete one key (no-op if it is not there).
"""
from __future__ import annotations

import contextlib
import functools
import json
import os

from config import APP_ID, fallback_base_dir

SETTINGS_FILE_NAME = "settings.json"

# Values that could not be written to disk (read-only home, full disk, ...).
# They are still honoured for the rest of the session. Otherwise a choice the user just made would silently not take
# effect, because every read goes back to the file.
_unsaved: dict = {}

# Sentinel meaning "the stored value does not fit the expected type" (None is a legitimate stored value).
_MISSING = object()


@functools.lru_cache(maxsize=1)
def _config_dir() -> str:
    """Return the application's config folder, resolved on first use and then cached."""
    # Resolved lazily so that GTK need not be imported at module load time.
    try:
        from gi.repository import GLib
        base = GLib.get_user_config_dir()
    except Exception:
        base = fallback_base_dir("config")
    return os.path.join(base, APP_ID)


def _config_path() -> str:
    """Return the full path of the settings file."""
    return os.path.join(_config_dir(), SETTINGS_FILE_NAME)


def _quarantine(path: str) -> None:
    """Move an unusable settings file aside (to settings.json.corrupt).

    This keeps the next write from silently destroying data the user may want to recover.
    """
    with contextlib.suppress(OSError):
        os.replace(path, path + ".corrupt")


def _is_readable(path: str) -> bool:
    """Return True if the first byte of *path* can be read."""
    try:
        with open(path, "rb") as settings_file:
            settings_file.read(1)
        return True
    except OSError:
        return False


def _read_saved_settings(path: str) -> dict | None:
    """Return the settings stored on disk.

    Returns:
        {} if there are none or the file is damaged (it is set aside first), or None if the file exists but cannot
        be read right now (it is then left alone).
    """
    try:
        with open(path, encoding="utf-8") as settings_file:
            loaded = json.load(settings_file)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # OSError: unreadable right now. ValueError: not valid JSON (hand-edited or damaged); keep a copy before it
        # is overwritten.
        if not os.path.exists(path):
            return {}
        if not _is_readable(path):
            return None
        _quarantine(path)
        return {}
    if isinstance(loaded, dict):
        return loaded
    _quarantine(path)
    return {}


def load() -> dict:
    """Return all saved settings, merged with values that could not be written; empty if there are none."""
    saved = _read_saved_settings(_config_path())
    if saved is None:
        return dict(_unsaved)
    return {**saved, **_unsaved} if _unsaved else saved


def save(data: dict) -> bool:
    """Overwrite the settings file with *data* atomically (temp file, fsync, then rename).

    Returns:
        False if the file could not be written.
    """
    path = _config_path()
    temp_path = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as temp_file:
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
        return True
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(temp_path)
        return False


def _as_int(value):
    """Return *value* as an int, or _MISSING. Booleans are rejected; whole floats are accepted."""
    if isinstance(value, bool):
        return _MISSING
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return _MISSING


def _as_float(value):
    """Return *value* as a float, or _MISSING. Booleans are rejected."""
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if is_number else _MISSING


def _fits(value, default):
    """Return *value* converted to the type of *default*, or _MISSING if it does not fit."""
    if isinstance(default, bool):
        return value if isinstance(value, bool) else _MISSING
    if isinstance(default, int):
        return _as_int(value)
    if isinstance(default, float):
        return _as_float(value)
    if isinstance(default, (str, list, dict)):
        return value if isinstance(value, type(default)) else _MISSING
    return value


def get(key: str, default=None):
    """Read a single key from the saved settings.

    When *default* is a bool, int, float, str, list or dict, a stored value of a different type (a hand-edited or
    damaged settings.json, or one written by another version) is ignored and *default* is returned instead, so no
    caller can be crashed by a bad value. With a default of None the stored value is returned as-is and the caller
    must validate it.
    """
    data = load()
    if key not in data:
        return default
    value = _fits(data[key], default) if default is not None else data[key]
    return default if value is _MISSING else value


def set(key: str, value) -> None:  # noqa: A001 — public API name used as app_settings.set(...)
    """Write a single key, merging with any previously saved settings."""
    # load() already includes any not-yet-saved values.
    data = load()
    data[key] = value
    if save(data):
        # Everything, including earlier unsaved values, is on disk now.
        _unsaved.clear()
    else:
        _unsaved[key] = value


def remove(key: str) -> None:
    """Delete a single key so that the setting goes back to its default; no-op if it is not stored."""
    _unsaved.pop(key, None)
    data = load()
    if key in data:
        del data[key]
        save(data)
