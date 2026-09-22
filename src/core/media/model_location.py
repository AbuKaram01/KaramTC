# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/model_location.py — Which speech-model folder to use, and whether it is usable.
"""
from __future__ import annotations

import glob
import os
from typing import NamedTuple

from core.media import model_store
from core.media.constants import SOURCE_CUSTOM


class ModelStatus(NamedTuple):
    ready: bool
    message: str


def problems_with_model_dir(path: str) -> list[str]:
    """What is missing from a faster-whisper (CTranslate2) model folder; empty if it is usable."""
    if not path:
        return ["No folder chosen."]
    if not os.path.isdir(path):
        return [f"Folder not found: {path}"]
    problems = [
        f"{name} is missing" for name in ("model.bin", "config.json")
        if not os.path.isfile(os.path.join(path, name))
    ]
    has_vocabulary = (
        os.path.isfile(os.path.join(path, "tokenizer.json"))
        or glob.glob(os.path.join(glob.escape(path), "vocabulary.*"))
    )
    if not has_vocabulary:
        problems.append("tokenizer.json or vocabulary.json is missing")
    return problems


def model_status(source: str, custom_dir: str, model_id: str | None = None) -> ModelStatus:
    """Whether transcription can start with this choice, and a sentence saying so.

    *model_id* is which downloadable model is chosen (the default one if not given)."""
    if source == SOURCE_CUSTOM:
        problems = problems_with_model_dir(custom_dir)
        if problems:
            return ModelStatus(False, problems[0])
        return ModelStatus(True, f"Using the model in {custom_dir}")
    model = model_store.get_model(model_id)
    if model_store.is_downloaded(model_id=model.id):
        return ModelStatus(True, f"{model.label} is ready")
    note = " (a partial download can be continued)" if model_store.has_partial_download(model_id=model.id) else ""
    return ModelStatus(False, f"{model.label} is not downloaded yet{note}")
