# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Saved progress of an interrupted transcription.

Every segment is appended to a small file the moment it is decoded, whether or not resuming is enabled, so a stop or
a crash never throws away hours of work. The file is only *used* when the user asked to resume, and only if it still
matches: same media file (size and modification time), same model, same language. Anything else is discarded rather
than trusted.

The file holds one JSON record per line: a header (format version, media fingerprint, model signature, language and
the number of carried-over segments) followed by one record per segment.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass

from config import user_data_dir
from core.media.segments import Segment

# Format version of the journal header; a journal with another version is not used.
_VERSION = 1


def default_journal_dir() -> str:
    """Return the folder where the journals are kept."""
    return os.path.join(user_data_dir(), "transcripts")


def model_signature(model_dir: str) -> dict:
    """Return a signature that identifies a model folder well enough to notice that it was replaced."""
    try:
        size = os.path.getsize(os.path.join(model_dir, "model.bin"))
    except OSError:
        size = None
    return {"path": os.path.realpath(model_dir), "size": size}


def media_fingerprint(media_path: str) -> list | None:
    """Return [size, modification time] of the media file, or None if it cannot be read."""
    try:
        stat = os.stat(media_path)
    except OSError:
        return None
    return [stat.st_size, stat.st_mtime]


def plan_resume(saved: list[Segment], carried: int = 0) -> list[Segment]:
    """Return the already-transcribed segments to keep when continuing.

    The last one is deliberately dropped: it is the one being finished when the job stopped, so the likeliest to be
    cut off. It is transcribed again with everything after it.

    Args:
        saved: The segments read from the journal.
        carried: How many segments an earlier resume had already carried over. If nothing new was produced since,
            they have all been through this once and are kept, so that stopping again right after resuming does
            not lose a segment each time.
    """
    if carried and len(saved) == carried:
        return list(saved)
    return list(saved[:-1])


@dataclass
class PartialTranscript:
    """The saved progress of an interrupted transcription, as read from the journal."""

    segments: list[Segment]
    language: str
    # How many of the segments were already carried over from earlier runs.
    carried: int


class JournalWriter:
    """Append segments to the journal.

    A failure to write (disk full, ...) is reported once and then ignored: saving progress must never stop the job.

    Args:
        path: The journal file to append to; None makes the writer do nothing.
        warn: Called with a message for the user when writing fails.
    """

    def __init__(self, path: str | None, warn: Callable[[str], None]):
        self._warn = warn
        self._file = None
        if path is not None:
            self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115 — closed by close()

    def write_line(self, record: dict) -> None:
        """Append *record* as one JSON line and force it to disk, so that a crash loses at most the line in progress."""
        if self._file is None:
            return
        try:
            self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._file.flush()
            os.fsync(self._file.fileno())
        except OSError as exc:
            self._warn(f"Could not save transcription progress ({exc.strerror or exc}); continuing without it.")
            self.close()

    def append(self, segment: Segment) -> None:
        """Append one decoded segment to the journal."""
        self.write_line({"s": segment.start, "e": segment.end, "t": segment.text})

    def close(self) -> None:
        """Close the journal file; safe to call more than once."""
        if self._file is not None:
            with contextlib.suppress(OSError):
                self._file.close()
            self._file = None


class TranscriptJournal:
    """The saved progress of transcriptions, one journal file per media file.

    Args:
        root: The folder for the journal files; defaults to default_journal_dir().
        warn: Called with a message for the user when progress cannot be saved.
    """

    def __init__(self, root: str | None = None, warn: Callable[[str], None] = lambda _message: None):
        self._root = root or default_journal_dir()
        self._warn = warn

    def _path(self, media_path: str) -> str:
        """Return the journal file of *media_path*, named after a hash of its resolved path."""
        key = hashlib.sha1(os.path.realpath(media_path).encode("utf-8")).hexdigest()
        return os.path.join(self._root, f"{key}.jsonl")

    def has_saved(self, media_path: str) -> bool:
        """Whether an interrupted transcription of this file left segments behind."""
        # A header and at least one segment.
        return len(self._read_records(self._path(media_path))) > 1

    def drop(self, media_path: str) -> None:
        """Delete the saved progress of *media_path*, if any."""
        with contextlib.suppress(OSError):
            os.remove(self._path(media_path))

    def load(
        self, media_path: str, model: dict, language: str | None,
    ) -> tuple[PartialTranscript | None, str | None]:
        """Return the saved progress of *media_path* if it can be continued.

        Returns:
            (progress, None) if it can be continued, else (None, why not). The reason is None when there is nothing
            to report: no journal, or one without segments or with an invalid segment record.
        """
        records = self._read_records(self._path(media_path))
        if not records:
            return None, None
        header, segments = records[0], [self._segment(record) for record in records[1:]]
        mismatch = self._mismatch(header, media_path, model, language)
        if mismatch:
            return None, mismatch
        if not segments or None in segments:
            return None, None
        return PartialTranscript(segments, header["language"], int(header.get("carried", 0))), None

    def start(
        self, media_path: str, model: dict, language: str, kept: list[Segment],
    ) -> JournalWriter:
        """Begin a fresh journal holding the segments carried over from an earlier run.

        If the file cannot be created, a warning is sent and a writer that does nothing is returned.
        """
        path = self._path(media_path)
        try:
            os.makedirs(self._root, exist_ok=True)
            with open(path, "w", encoding="utf-8"):
                pass
        except OSError as exc:
            self._warn(f"Could not save transcription progress ({exc.strerror or exc}); continuing without it.")
            return JournalWriter(None, self._warn)
        writer = JournalWriter(path, self._warn)
        writer.write_line({
            "version": _VERSION, "media": media_fingerprint(media_path), "model": model,
            "language": language, "carried": len(kept),
        })
        for segment in kept:
            writer.append(segment)
        return writer

    @staticmethod
    def _read_records(path: str) -> list[dict]:
        """Return every readable record; reading stops at the first damaged line (a write cut short by a crash)."""
        records: list[dict] = []
        try:
            with open(path, encoding="utf-8") as journal_file:
                for line in journal_file:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        break
                    if not isinstance(record, dict):
                        break
                    records.append(record)
        except OSError:
            return []
        return records

    @staticmethod
    def _segment(record: dict) -> Segment | None:
        """Convert a journal record to a Segment, or None if its fields are missing or inconsistent."""
        try:
            start, end, text = float(record["s"]), float(record["e"]), str(record["t"])
        except (KeyError, TypeError, ValueError):
            return None
        return Segment(start, end, text) if 0 <= start <= end else None

    @staticmethod
    def _mismatch(header: dict, media_path: str, model: dict, language: str | None) -> str | None:
        """Return why the journal cannot be used for this media file, model and language, or None if it can."""
        if header.get("version") != _VERSION or not isinstance(header.get("language"), str):
            return "it was written by a different version"
        if header.get("media") != media_fingerprint(media_path):
            return "the file has changed since"
        if header.get("model") != model:
            return "a different speech model is selected now"
        if language is not None and language != header["language"]:
            return "it was made for a different language"
        return None
