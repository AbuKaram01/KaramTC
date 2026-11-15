# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""How many CPU threads OCR may use.

Tesseract does its recognition with OpenMP threads. Left alone it starts up to 4 of them *whatever the machine has*
(measured: 4 threads on a 1-core machine, where a single thread was 3x faster), and on a laptop the rest of the system
then crawls while a long book runs. OMP_THREAD_LIMIT caps the count; the choices below are what OCR Settings offers.
"""

from __future__ import annotations

import os

# The CPU-usage choices as (id, display name) pairs, in display order.
CPU_USAGE_OPTIONS = [
    ("auto",     "Auto"),
    ("low",      "Low"),
    ("balanced", "Balanced"),
    ("max",      "Maximum"),
]
DEFAULT_CPU_USAGE = "auto"

# What Tesseract uses by default for recognition.
_ENGINE_DEFAULT_THREADS = 4
_VALID_CPU_USAGES = frozenset(value for value, _label in CPU_USAGE_OPTIONS)


def cpu_cores() -> int:
    """Return the CPU cores this process may run on (honours affinity limits such as containers)."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def normalize_cpu_usage(value) -> str:
    """Return *value* if it is one of the CPU-usage ids, else DEFAULT_CPU_USAGE."""
    return value if isinstance(value, str) and value in _VALID_CPU_USAGES else DEFAULT_CPU_USAGE


def threads_for_usage(usage, cores: int | None = None) -> int | None:
    """Return the thread limit for a CPU-usage choice, or None to leave Tesseract alone.

    The choices map as follows:

      auto     - never more threads than the machine has cores (so 1-3 core machines stop oversubscribing); with 4+
                 cores that is Tesseract's own default, so None.
      low      - 1: the computer stays responsive, and for Tesseract this is often just as fast.
      balanced - half the cores.
      max      - all cores.

    Args:
        usage: One of the ids in CPU_USAGE_OPTIONS; any other value is treated as DEFAULT_CPU_USAGE.
        cores: The number of cores to assume; defaults to cpu_cores().
    """
    cores = max(1, cores if cores is not None else cpu_cores())
    usage = normalize_cpu_usage(usage)
    if usage == "low":
        return 1
    if usage == "balanced":
        return max(1, cores // 2)
    if usage == "max":
        return cores
    return None if cores >= _ENGINE_DEFAULT_THREADS else cores
