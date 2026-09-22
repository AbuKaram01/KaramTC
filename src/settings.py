# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
settings.py — Persistent user preferences (stored in the XDG config directory).

Saved to: ~/.config/<APP_ID>/settings.json  (see config.APP_ID)

Public API:
  load()              → dict  : Returns all saved settings (empty dict if none).
  save(data)                  : Overwrites the settings file atomically.
  get(key, default)   → any   : Reads one key from disk.
  set(key, value)             : Writes one key to disk (merges with existing data).
  remove(key)                 : Deletes one key (no-op if it isn't there).
"""
from __future__ import annotations

import contextlib
import functools
import json
import os

from config import APP_ID, fallback_base_dir

SETTINGS_FILE_NAME = "settings.json"

# Values that could not be written to disk (read-only home, full disk, …).
# They are still honoured for the rest of the session — otherwise a choice
# the user just made would silently not take effect, because every read goes
# back to the file.
_unsaved: dict = {}

_MISSING = object()


@functools.lru_cache(maxsize=1)
def _config_dir() -> str:
    # Resolved lazily so GTK need not be imported at module load time.
    try:
        from gi.repository import GLib
        base = GLib.get_user_config_dir()
    except Exception:
        base = fallback_base_dir("config")
    return os.path.join(base, APP_ID)


def _config_path() -> str:
    return os.path.join(_config_dir(), SETTINGS_FILE_NAME)


def _quarantine(path: str) -> None:
    """Moves an unreadable settings file aside (to settings.json.corrupt) so the
    next write doesn't silently destroy whatever the user may want to recover."""
    with contextlib.suppress(OSError):
        os.replace(path, path + ".corrupt")


def _is_readable(path: str) -> bool:
    try:
        with open(path, "rb") as settings_file:
            settings_file.read(1)
        return True
    except OSError:
        return False


def _read_saved_settings(path: str) -> dict | None:
    """
    The settings stored on disk: {} if there are none or the file is damaged
    (it is set aside first), or None if the file exists but cannot be read
    right now (it is then left alone).
    """
    try:
        with open(path, encoding="utf-8") as settings_file:
            loaded = json.load(settings_file)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # OSError: unreadable right now. ValueError: not valid JSON (hand-edited
        # or damaged) — keep a copy before it is overwritten.
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
    """Returns all saved settings. Returns an empty dict if there are none."""
    saved = _read_saved_settings(_config_path())
    if saved is None:
        return dict(_unsaved)
    return {**saved, **_unsaved} if _unsaved else saved


def save(data: dict) -> bool:
    """Atomically overwrites the settings file with *data*. False if it could not be written."""
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
    if isinstance(value, bool):
        return _MISSING
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return _MISSING


def _as_float(value):
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if is_number else _MISSING


def _fits(value, default):
    """*value* converted to the type of *default*, or _MISSING if it doesn't fit."""
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
    """
    Reads a single key from the saved settings.

    When *default* is a bool, int, float, str, list or dict, a stored value of
    a different type (a hand-edited or damaged settings.json, or one written
    by another version) is ignored and *default* is returned instead, so no
    caller can be crashed by a bad value. With a default of None the stored
    value is returned as-is and the caller must validate it.
    """
    data = load()
    if key not in data:
        return default
    value = _fits(data[key], default) if default is not None else data[key]
    return default if value is _MISSING else value


def set(key: str, value) -> None:  # noqa: A001 — public API name used as app_settings.set(...)
    """Writes a single key, merging with any previously saved settings."""
    data = load()                # already includes any not-yet-saved values
    data[key] = value
    if save(data):
        _unsaved.clear()         # everything, including earlier unsaved values, is on disk now
    else:
        _unsaved[key] = value


def remove(key: str) -> None:
    """Deletes a single key so the setting goes back to its default."""
    _unsaved.pop(key, None)
    data = load()
    if key in data:
        del data[key]
        save(data)
