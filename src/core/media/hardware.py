# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/hardware.py — Which device runs the speech model.
"""
from __future__ import annotations

import os
from typing import NamedTuple

from core.media.constants import DEVICE_CPU, DEVICE_GPU


class DeviceChoice(NamedTuple):
    device: str          # faster-whisper's names: "cpu" or "cuda"
    compute_type: str


CPU = DeviceChoice("cpu", "int8")
GPU = DeviceChoice("cuda", "float16")


def gpu_available() -> bool:
    """
    Best-effort check for a usable CUDA GPU, using ctranslate2's own device
    detection (already a dependency of faster-whisper). Any failure — no GPU,
    no driver, a CPU-only build, the package missing — simply means "no".
    """
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolve_device(setting: str) -> DeviceChoice:
    """Maps the "auto" / "cpu" / "gpu" setting to the device and precision to load the model with."""
    if setting == DEVICE_CPU:
        return CPU
    if setting == DEVICE_GPU:
        return GPU
    return GPU if gpu_available() else CPU


def default_cpu_threads() -> int:
    """CPU cores this process may use (honours affinity limits such as containers)."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)
