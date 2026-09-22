# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
core/media/engine.py — The speech-recognition engine (faster-whisper).

The pipeline talks to the small WhisperEngine interface only, so it can be
tested with a fake model, and faster-whisper (a heavy import) is loaded only
when a transcription actually starts.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from core.media.constants import DEVICE_AUTO, SAMPLE_RATE
from core.media.errors import SpeechEngineMissingError
from core.media.hardware import CPU, DeviceChoice, resolve_device
from core.media.job import EngineSettings
from core.media.segments import Segment

# The decoding settings of KaramVT. VAD skips silence (so Whisper doesn't
# invent words there); the repetition penalty and conditioning on the previous
# text keep long recordings consistent.
_TRANSCRIBE_OPTIONS = {
    "beam_size": 5,
    "vad_filter": True,
    "vad_parameters": {"min_silence_duration_ms": 500},
    "repetition_penalty": 1.1,
    "condition_on_previous_text": True,
}

_GPU_LIBRARY_HINT = (
    "The GPU could not be used (CUDA libraries are missing or incompatible). "
    "Set Processing device to CPU in Speech Settings."
)
_GPU_ERROR_MARKERS = ("cublas", "cudnn", "cuda")


@dataclass(frozen=True)
class StreamInfo:
    language: str
    language_probability: float
    duration: float     # seconds of the audio that was passed in


def import_faster_whisper():
    """The faster_whisper module, or a SpeechEngineMissingError saying how to install it."""
    try:
        import faster_whisper
    except ImportError as exc:
        raise SpeechEngineMissingError(
            "The speech engine (faster-whisper) is not installed.\n"
            "Install it with:  pip install faster-whisper"
        ) from exc
    return faster_whisper


def speech_engine_installed() -> bool:
    """Whether faster-whisper can be imported — checked without importing it."""
    import importlib.util
    return importlib.util.find_spec("faster_whisper") is not None


def explain_engine_error(error: Exception) -> Exception:
    """Turns a CUDA library failure into an actionable message; anything else is returned unchanged."""
    text = str(error).lower()
    if any(marker in text for marker in _GPU_ERROR_MARKERS):
        return RuntimeError(f"{_GPU_LIBRARY_HINT}\n\nDetails: {error}")
    return error


class WhisperEngine:
    """A loaded speech model."""

    def __init__(self, model: Any):
        """:param model: a faster_whisper.WhisperModel (or anything with the same transcribe())."""
        self._model = model

    @classmethod
    def load(cls, settings: EngineSettings, notify: Callable[[str], None] = lambda _message: None) -> WhisperEngine:
        faster_whisper = import_faster_whisper()
        choice = resolve_device(settings.device)
        try:
            return cls(cls._load_model(faster_whisper, settings, choice))
        except Exception as exc:
            if settings.device != DEVICE_AUTO or choice == CPU:
                raise explain_engine_error(exc) from exc
            notify("GPU unavailable — continuing on the CPU.")
            return cls(cls._load_model(faster_whisper, settings, CPU))

    @staticmethod
    def _load_model(faster_whisper, settings: EngineSettings, choice: DeviceChoice):
        return faster_whisper.WhisperModel(
            settings.model_dir,
            device=choice.device,
            compute_type=choice.compute_type,
            cpu_threads=max(1, settings.cpu_threads),
        )

    @staticmethod
    def load_audio(path: str):
        """The media file's audio as 16 kHz mono samples. Video files work too: only the audio track is read."""
        from faster_whisper.audio import decode_audio
        return decode_audio(path, sampling_rate=SAMPLE_RATE)

    def transcribe(
        self, audio: Any, language: str | None, offset: float = 0.0,
    ) -> tuple[StreamInfo, Iterator[Segment]]:
        """
        Starts transcribing *audio* — a path, or samples from load_audio().
        *language* None detects it. Timestamps are shifted by *offset* seconds,
        for audio that was cut from the middle of the file.

        Returns once the language is known; the segments are produced lazily as
        the audio is decoded, so stopping between segments is responsive.
        """
        try:
            raw_segments, info = self._model.transcribe(audio, language=language, **_TRANSCRIBE_OPTIONS)
        except Exception as exc:
            raise explain_engine_error(exc) from exc
        stream_info = StreamInfo(info.language, info.language_probability, info.duration)
        return stream_info, self._shifted(raw_segments, offset)

    @staticmethod
    def _shifted(raw_segments, offset: float) -> Iterator[Segment]:
        for raw in raw_segments:
            yield Segment(raw.start + offset, raw.end + offset, raw.text)
