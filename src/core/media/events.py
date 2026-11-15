# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The progress-callback protocol of the transcription pipeline.

The pipeline reports progress by calling ``progress_cb(kind, *args)`` from its worker thread. The kinds, with the
arguments that follow them:

    STAGE     (label)                          a new stage began
    LANGUAGE  (code, probability)              the spoken language is known
    PROGRESS  (position_s, duration_s, text)   a segment was decoded; *text* is its words
    NOTE      (message)                        something worth telling the user, without changing stage
"""
from __future__ import annotations

STAGE = "stage"
LANGUAGE = "language"
PROGRESS = "progress"
NOTE = "note"
