import os
import threading
from types import SimpleNamespace

import pytest

from core.media import (
    EngineSettings, MediaRequest, MediaSettings, NoSpeechError, SpeechEngineMissingError,
    TranscriptionCancelledError, events, run_media_transcription,
)
from core.media.constants import SAMPLE_RATE
from core.media.engine import StreamInfo, WhisperEngine
from core.media.journal import TranscriptJournal, model_signature, plan_resume
from core.media.segments import Segment

SCRIPT = [(0.0, 2.0, " one "), (2.0, 4.0, "two"), (4.0, 6.0, "three"), (6.0, 8.0, "four")]
TOTAL = 8.0


class FakeEngine:
    """Stands in for WhisperEngine: a deterministic 8-second recording."""

    def __init__(self, script=SCRIPT):
        self.script = script
        self.calls = []             # (audio kind, language, offset) of every transcribe()

    def load_audio(self, path):
        return list(range(int(TOTAL * SAMPLE_RATE)))

    def transcribe(self, audio, language, offset=0.0):
        self.calls.append(("path" if isinstance(audio, str) else len(audio), language, offset))
        duration = TOTAL if isinstance(audio, str) else len(audio) / SAMPLE_RATE
        segments = (Segment(s, e, t) for s, e, t in self.script if s >= offset)
        return StreamInfo(language or "en", 0.97, duration), segments


@pytest.fixture
def model_dir(tmp_path):
    folder = tmp_path / "model"
    folder.mkdir()
    for name in ("model.bin", "config.json", "vocabulary.json"):
        (folder / name).write_bytes(b"x" * 10)
    return str(folder)


@pytest.fixture
def media(tmp_path):
    path = tmp_path / "talk.mp4"
    path.write_bytes(b"not really a video")
    return str(path)


def make_request(media, model_dir, tmp_path, **settings):
    return MediaRequest(media, str(tmp_path / "talk.txt"), MediaSettings(**settings), EngineSettings(model_dir))


def run(request, tmp_path, engine=None, cancel=None, events_log=None):
    engine = engine or FakeEngine()
    journal = TranscriptJournal(str(tmp_path / "journal"))
    callback = (lambda *args: events_log.append(args)) if events_log is not None else None
    return run_media_transcription(request, callback, cancel or threading.Event(), lambda *_: engine, journal)


def test_a_transcript_is_written_with_progress_and_language_events(media, model_dir, tmp_path):
    log = []
    result = run(make_request(media, model_dir, tmp_path), tmp_path, events_log=log)

    assert (tmp_path / "talk.txt").read_text() == "one two three four\n"        # continuous text by default
    assert (result.language, result.language_probability, result.segment_count, result.duration) == ("en", 0.97, 4, TOTAL)
    assert result.text == "one two three four" and result.resumed_segments == 0
    progress = [event for event in log if event[0] == events.PROGRESS]
    assert [event[1] for event in progress] == [2.0, 4.0, 6.0, 8.0] and progress[0][3] == "one"
    assert (events.LANGUAGE, "en", 0.97) in log
    assert [event[1] for event in log if event[0] == events.STAGE] == ["Loading the speech model…", "Transcribing…", "Saving…"]
    assert not (tmp_path / "talk.txt.part").exists()


def test_the_lines_layout_and_timestamps_are_honoured(media, model_dir, tmp_path):
    result = run(make_request(media, model_dir, tmp_path, text_layout="lines", timestamps=True), tmp_path)
    assert (tmp_path / "talk.txt").read_text() == "[0:00:00] one\n[0:00:02] two\n[0:00:04] three\n[0:00:06] four\n"
    assert result.text == "one\ntwo\nthree\nfour"


def test_a_chosen_language_is_passed_on_and_not_reported_as_detected(media, model_dir, tmp_path):
    engine = FakeEngine()
    result = run(make_request(media, model_dir, tmp_path, language="ar", output_format="srt"), tmp_path, engine)
    assert engine.calls == [("path", "ar", 0.0)] and result.language_probability is None
    assert (tmp_path / "talk.txt").read_text().startswith("1\n00:00:00,000 --> 00:00:02,000\none\n")


def test_a_recording_without_speech_is_an_error_and_leaves_no_progress(media, model_dir, tmp_path):
    with pytest.raises(NoSpeechError):
        run(make_request(media, model_dir, tmp_path), tmp_path, FakeEngine(script=[(0, 1, "  ")]))
    assert not os.path.exists(tmp_path / "talk.txt")
    assert os.listdir(tmp_path / "journal") == []


def test_missing_input_or_unusable_model_fail_before_loading_anything(media, model_dir, tmp_path):
    loaded = []
    request = make_request(str(tmp_path / "gone.mp4"), model_dir, tmp_path)
    with pytest.raises(RuntimeError, match="File not found"):
        run_media_transcription(request, None, threading.Event(), lambda *_: loaded.append(1))
    request = make_request(media, str(tmp_path / "no-model"), tmp_path)
    with pytest.raises(RuntimeError, match="speech model is not usable"):
        run_media_transcription(request, None, threading.Event(), lambda *_: loaded.append(1))
    assert loaded == []


def interrupted_run(media, model_dir, tmp_path, after_segments=2, **settings):
    """Runs the pipeline and presses Stop once *after_segments* segments were produced."""
    cancel = threading.Event()

    def stop_after(kind, *args):
        if kind == events.PROGRESS and args[0] >= after_segments * 2.0:
            cancel.set()
    journal = TranscriptJournal(str(tmp_path / "journal"))
    with pytest.raises(TranscriptionCancelledError):
        run_media_transcription(make_request(media, model_dir, tmp_path, **settings), stop_after, cancel,
                                lambda *_: FakeEngine(), journal)


def test_stopping_keeps_the_segments_and_resuming_gives_the_same_transcript(media, model_dir, tmp_path):
    interrupted_run(media, model_dir, tmp_path)
    saved = TranscriptJournal(str(tmp_path / "journal"))._read_records(next(
        str(tmp_path / "journal" / name) for name in os.listdir(tmp_path / "journal")))
    assert [record["t"] for record in saved[1:]] == [" one ", "two"]

    engine = FakeEngine()
    log = []
    result = run(make_request(media, model_dir, tmp_path, resume=True, text_layout="lines"), tmp_path, engine, events_log=log)

    assert engine.calls == [(int((TOTAL - 2.0) * SAMPLE_RATE), "en", 2.0)]       # continued from the end of "one"
    assert (tmp_path / "talk.txt").read_text() == "one\ntwo\nthree\nfour\n"
    assert result.resumed_segments == 1 and result.language_probability is None
    assert any(event[0] == events.NOTE and "join point" in event[1] for event in log)
    assert os.listdir(tmp_path / "journal") == []


def test_saved_progress_is_ignored_unless_resuming_is_switched_on(media, model_dir, tmp_path):
    interrupted_run(media, model_dir, tmp_path)
    engine = FakeEngine()
    run(make_request(media, model_dir, tmp_path, resume=False), tmp_path, engine)
    assert engine.calls == [("path", None, 0.0)]


def test_saved_progress_that_no_longer_matches_is_discarded(media, model_dir, tmp_path):
    interrupted_run(media, model_dir, tmp_path)
    with open(media, "ab") as changed:
        changed.write(b"edited")
    engine, log = FakeEngine(), []
    run(make_request(media, model_dir, tmp_path, resume=True), tmp_path, engine, events_log=log)
    assert engine.calls == [("path", None, 0.0)]
    assert any(event[0] == events.NOTE and "file has changed" in event[1] for event in log)


def test_a_language_that_differs_from_the_saved_one_starts_over(media, model_dir, tmp_path):
    interrupted_run(media, model_dir, tmp_path)
    engine = FakeEngine()
    run(make_request(media, model_dir, tmp_path, resume=True, language="fr"), tmp_path, engine)
    assert engine.calls == [("path", "fr", 0.0)]


def test_stopping_right_after_a_resume_does_not_lose_another_segment():
    saved = [Segment(0, 1, "a"), Segment(1, 2, "b")]
    assert plan_resume(saved) == [saved[0]]
    assert plan_resume(saved, carried=2) == saved
    assert plan_resume(saved + [Segment(2, 3, "c")], carried=2) == saved


def test_a_journal_cut_short_by_a_crash_is_still_readable(media, model_dir, tmp_path):
    interrupted_run(media, model_dir, tmp_path, after_segments=3)
    journal_file = tmp_path / "journal" / os.listdir(tmp_path / "journal")[0]
    with open(journal_file, "a", encoding="utf-8") as damaged:
        damaged.write('{"s": 6.0, "e": 7')          # a write that never finished
    partial, why = TranscriptJournal(str(tmp_path / "journal")).load(media, model_signature(model_dir), None)
    assert why is None and [s.text.strip() for s in partial.segments] == ["one", "two", "three"]


def test_a_journal_that_cannot_be_written_only_warns(media, model_dir, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    warnings = []
    journal = TranscriptJournal(str(blocker / "journal"), warn=warnings.append)
    result = run_media_transcription(
        make_request(media, model_dir, tmp_path), None, threading.Event(), lambda *_: FakeEngine(), journal,
    )
    assert result.segment_count == 4 and warnings and "continuing without it" in warnings[0]


# ── The faster-whisper adapter ──────────────────────────────────────

class FakeWhisperModel:
    def __init__(self, segments, language="ar"):
        self.segments, self.language, self.received = segments, language, None

    def transcribe(self, audio, language=None, **options):
        self.received = (audio, language, options)
        return iter(self.segments), SimpleNamespace(language=self.language, language_probability=0.9, duration=12.5)


def test_the_adapter_shifts_timestamps_and_passes_the_decoding_options():
    raw = [SimpleNamespace(start=0.5, end=1.5, text="a"), SimpleNamespace(start=1.5, end=2.0, text="b")]
    model = FakeWhisperModel(raw)
    info, stream = WhisperEngine(model).transcribe("file.mp3", None, offset=10.0)
    assert (info.language, info.language_probability, info.duration) == ("ar", 0.9, 12.5)
    assert [(s.start, s.end) for s in stream] == [(10.5, 11.5), (11.5, 12.0)]
    audio, language, options = model.received
    assert (audio, language) == ("file.mp3", None) and options["vad_filter"] is True and options["beam_size"] == 5


def test_a_missing_speech_engine_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "faster_whisper", None)
    with pytest.raises(SpeechEngineMissingError, match="pip install faster-whisper"):
        WhisperEngine.load(EngineSettings("/nowhere"))


def test_loading_falls_back_to_the_cpu_when_the_automatic_gpu_choice_fails(monkeypatch):
    attempts = []

    class FakeModule:
        @staticmethod
        def WhisperModel(path, device, compute_type, cpu_threads):
            attempts.append((device, compute_type, cpu_threads))
            if device == "cuda":
                raise RuntimeError("Library libcublas.so.12 is not found")
            return object()

    monkeypatch.setattr("core.media.engine.import_faster_whisper", lambda: FakeModule)
    monkeypatch.setattr("core.media.hardware.gpu_available", lambda: True)
    notes = []
    WhisperEngine.load(EngineSettings("/m", device="auto", cpu_threads=0), notes.append)
    assert attempts == [("cuda", "float16", 1), ("cpu", "int8", 1)] and "CPU" in notes[0]

    with pytest.raises(RuntimeError, match="Processing device to CPU"):
        WhisperEngine.load(EngineSettings("/m", device="gpu"))


def test_audio_and_video_files_are_decoded_for_real(tmp_path):
    av = pytest.importorskip("av")
    numpy = pytest.importorskip("numpy")
    pytest.importorskip("faster_whisper")
    from core.media import probe_media

    wav, video, silent_video = (str(tmp_path / name) for name in ("tone.wav", "clip.mp4", "mute.mp4"))
    samples = (numpy.sin(numpy.linspace(0, 440 * 2 * numpy.pi * 2, 16000 * 2)) * 0.3 * 32767).astype("int16")

    def write(path, with_audio, with_video):
        with av.open(path, "w") as container:
            audio = container.add_stream("pcm_s16le" if path.endswith(".wav") else "aac", rate=16000, layout="mono") if with_audio else None
            if with_video:
                stream = container.add_stream("mpeg4", rate=5)
                stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
                for _ in range(10):
                    for packet in stream.encode(av.VideoFrame(64, 64, "yuv420p")):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)
            if audio is not None:
                frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
                frame.sample_rate = 16000
                for packet in audio.encode(frame):
                    container.mux(packet)
                for packet in audio.encode():
                    container.mux(packet)

    write(wav, True, False)
    write(video, True, True)
    write(silent_video, False, True)
    for path in (wav, video):
        assert abs(len(WhisperEngine.load_audio(path)) / SAMPLE_RATE - 2.0) < 0.2
        info = probe_media(path)
        assert info.has_audio and abs(info.duration - 2.0) < 0.3
    assert probe_media(silent_video).has_audio is False
