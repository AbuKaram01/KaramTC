# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Which speech-model folder to use, and whether it is usable."""
from __future__ import annotations

import glob
import os
from typing import NamedTuple

from core.media import model_store
from core.media.constants import SOURCE_CUSTOM


class ModelStatus(NamedTuple):
    """Whether transcription can start with the chosen model, and a sentence for the user saying so."""

    ready: bool
    message: str


def problems_with_model_dir(path: str) -> list[str]:
    """Return what is missing from a faster-whisper (CTranslate2) model folder; empty if it is usable."""
    if not path:
        return ["No folder chosen."]
    if not os.path.isdir(path):
        return [f"Folder not found: {path}"]
    problems = [
        f"{name} is missing" for name in ("model.bin", "config.json")
        if not os.path.isfile(os.path.join(path, name))
    ]
    # glob.escape() makes a folder name that contains wildcard characters ([, *, ?) match literally.
    has_vocabulary = (
        os.path.isfile(os.path.join(path, "tokenizer.json"))
        or glob.glob(os.path.join(glob.escape(path), "vocabulary.*"))
    )
    if not has_vocabulary:
        problems.append("tokenizer.json or vocabulary.json is missing")
    return problems


def model_status(source: str, custom_dir: str, model_id: str | None = None) -> ModelStatus:
    """Return whether transcription can start with this choice, and a sentence saying so.

    Args:
        source: SOURCE_MANAGED (the model KaramTC downloads) or SOURCE_CUSTOM (a folder the user chose).
        custom_dir: The folder of the custom model; used only with SOURCE_CUSTOM.
        model_id: Which downloadable model is chosen (the default one if not given); used only with SOURCE_MANAGED.
    """
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
