# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/book/errors.py — Exceptions of the book pipeline.
"""
from __future__ import annotations


class CancelledError(Exception):
    """Raised when the user presses the Stop button; the job stays resumable."""
