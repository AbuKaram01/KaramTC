# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Run the tesseract child process.

It is polled rather than waited on, so a Stop request can kill it within a fraction of a second instead of waiting out
the whole time limit.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import threading
import time
from dataclasses import dataclass

from providers.ocr_types import OcrPageError
from providers.tesseract import program

_POLL_INTERVAL_S = 0.2
_KILL_WAIT_S = 2

# The Tesseract processes currently being waited on. If the app is quit while Tesseract is running (including from the
# "Quit anyway" prompt during an extraction), the child would otherwise be left behind, burning CPU until it finishes
# its page.
_active_processes: set[subprocess.Popen] = set()
_active_processes_lock = threading.Lock()


@dataclass
class ProcessOutput:
    """The captured output and exit status of a finished Tesseract process."""

    stdout: str
    stderr: str
    returncode: int


def terminate_active_processes() -> None:
    """Kill every Tesseract process this app started and is still waiting on."""
    with _active_processes_lock:
        processes = list(_active_processes)
    for process in processes:
        with contextlib.suppress(OSError):
            process.kill()


def _environment_for(threads: int | None) -> dict | None:
    """Return the environment for the child: None (inherit) unless a thread limit is requested.

    Auto mode on a machine with 4+ cores deliberately leaves the engine alone.
    """
    if not threads:
        return None
    return {**os.environ, "OMP_THREAD_LIMIT": str(max(1, int(threads)))}


def _start(command: list[str], threads: int | None, cwd: str | None = None) -> subprocess.Popen:
    """Start the process with piped output; raise RuntimeError if the program cannot be launched."""
    try:
        # Decode explicitly (and leniently): with text=True alone Python uses the locale encoding and would raise on a
        # stray non-UTF-8 byte.
        return subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=_environment_for(threads), cwd=cwd,
            # Keeps a console window from flashing up for every page on Windows.
            **program.quiet_window_options(),
        )
    except FileNotFoundError:
        raise RuntimeError("Could not launch tesseract — make sure it is installed")


def _kill(process: subprocess.Popen) -> None:
    """Kill the process, wait briefly for it to exit and close its pipes."""
    process.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=_KILL_WAIT_S)
    for pipe in (process.stdout, process.stderr):
        if pipe:
            pipe.close()


def _wait_for(process: subprocess.Popen, time_limit: float, cancel_event) -> ProcessOutput:
    """Poll the process until it finishes, is cancelled or exceeds *time_limit* seconds."""
    deadline = time.monotonic() + time_limit
    while True:
        try:
            stdout, stderr = process.communicate(timeout=_POLL_INTERVAL_S)
            return ProcessOutput(stdout, stderr, process.returncode)
        except subprocess.TimeoutExpired:
            pass
        if cancel_event is not None and cancel_event.is_set():
            _kill(process)
            raise RuntimeError("Cancelled by user")
        if time.monotonic() >= deadline:
            _kill(process)
            raise OcrPageError(
                f"Tesseract timed out ({int(time_limit)} s) — try a smaller image, "
                "or a lower resolution in OCR Settings \u2192 PDF page images"
            )


def run_tesseract(
    command: list[str], threads: int | None, time_limit: float, cancel_event, cwd: str | None = None,
) -> ProcessOutput:
    """Run *command* to completion, in the folder *cwd* (where the application is, if None).

    Args:
        command: The full command line.
        threads: CPU threads Tesseract may use; None leaves the choice to it.
        time_limit: Seconds to wait before the process is killed.
        cancel_event: Optional threading.Event; when set, the process is killed.
        cwd: The folder to start the process in; None keeps the application's own.

    Raises:
        RuntimeError: Tesseract cannot be launched, or the user cancelled.
        OcrPageError: The time limit was exceeded.
    """
    process = _start(command, threads, cwd)
    with _active_processes_lock:
        _active_processes.add(process)
    try:
        return _wait_for(process, time_limit, cancel_event)
    finally:
        with _active_processes_lock:
            _active_processes.discard(process)
