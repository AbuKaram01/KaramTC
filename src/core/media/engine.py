# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The speech-recognition engine (faster-whisper).

The pipeline talks to the small WhisperEngine interface only, so it can be tested with a fake model, and
faster-whisper (a heavy import) is loaded only when a transcription actually starts.
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

# The decoding settings of KaramVT. Voice activity detection (VAD) skips silence, so that Whisper does not invent
# words there; the repetition penalty and conditioning on the previous text keep long recordings consistent.
_TRANSCRIBE_OPTIONS = {
    "beam_size": 5,
    "vad_filter": True,
    "vad_parameters": {"min_silence_duration_ms": 500},
    "repetition_penalty": 1.1,
    "condition_on_previous_text": True,
}

# Shown instead of the raw error when a GPU run fails because of the CUDA libraries.
_GPU_LIBRARY_HINT = (
    "The GPU could not be used (CUDA libraries are missing or incompatible). "
    "Set Processing device to CPU in Speech Settings."
)
# Lower-case fragments that identify a missing or incompatible CUDA library in an error message.
_GPU_ERROR_MARKERS = ("cublas", "cudnn", "cuda")


@dataclass(frozen=True)
class StreamInfo:
    """What the engine learned about the audio before the first segment: the language and the duration."""

    language: str
    language_probability: float
    # Seconds of the audio that was passed in.
    duration: float


def import_faster_whisper():
    """Import and return the faster_whisper module.

    Raises:
        SpeechEngineMissingError: The package is not installed; the message says how to install it.
    """
    try:
        import faster_whisper
    except ImportError as exc:
        raise SpeechEngineMissingError(
            "The speech engine (faster-whisper) is not installed.\n"
            "Install it with:  pip install faster-whisper"
        ) from exc
    return faster_whisper


def speech_engine_installed() -> bool:
    """Return True if faster-whisper is installed, checked without importing it."""
    import importlib.util
    return importlib.util.find_spec("faster_whisper") is not None


def explain_engine_error(error: Exception) -> Exception:
    """Turn a CUDA library failure into an actionable message; return any other error unchanged."""
    text = str(error).lower()
    if any(marker in text for marker in _GPU_ERROR_MARKERS):
        return RuntimeError(f"{_GPU_LIBRARY_HINT}\n\nDetails: {error}")
    return error


class WhisperEngine:
    """A loaded speech model.

    Args:
        model: A faster_whisper.WhisperModel (or anything with the same transcribe()).
    """

    def __init__(self, model: Any):
        self._model = model

    @classmethod
    def load(cls, settings: EngineSettings, notify: Callable[[str], None] = lambda _message: None) -> WhisperEngine:
        """Load the speech model on the device that *settings* asks for.

        With the automatic device choice, a failure on the GPU falls back to the CPU instead of failing.

        Args:
            settings: Where the model is and which device to use.
            notify: Called with a message for the user when the engine falls back to the CPU.
        """
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
        """Return the media file's audio as 16 kHz mono samples. Video files work too: only the audio track is read."""
        from faster_whisper.audio import decode_audio
        return decode_audio(path, sampling_rate=SAMPLE_RATE)

    def transcribe(
        self, audio: Any, language: str | None, offset: float = 0.0,
    ) -> tuple[StreamInfo, Iterator[Segment]]:
        """Start transcribing *audio* and return the stream information with a lazy iterator of segments.

        Args:
            audio: A path, or samples from load_audio().
            language: The spoken language; None detects it.
            offset: Seconds added to every timestamp, for audio that was cut from the middle of the file.

        Returns:
            The stream information and the segments. The call returns once the language is known; the segments are
            produced lazily as the audio is decoded, so stopping between segments is responsive.
        """
        try:
            raw_segments, info = self._model.transcribe(audio, language=language, **_TRANSCRIBE_OPTIONS)
        except Exception as exc:
            raise explain_engine_error(exc) from exc
        stream_info = StreamInfo(info.language, info.language_probability, info.duration)
        return stream_info, self._shifted(raw_segments, offset)

    @staticmethod
    def _shifted(raw_segments, offset: float) -> Iterator[Segment]:
        """Convert the engine's raw segments to Segment objects, shifting their times by *offset* seconds."""
        for raw in raw_segments:
            yield Segment(raw.start + offset, raw.end + offset, raw.text)
