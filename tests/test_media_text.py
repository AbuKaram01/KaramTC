import pytest

from core.media import MEDIA_EXTENSIONS, WHISPER_LANGUAGES, language_name, languages_by_name, output_path_for
from core.media.constants import DEVICE_AUTO, DEVICE_CPU, DEVICE_GPU
from core.media.hardware import CPU, GPU, resolve_device
from core.media.model_location import model_status, problems_with_model_dir
from core.media.output import write_atomically
from core.media.segments import (
    Segment, format_clock, format_timestamp, plain_text, render, render_srt, render_text, render_vtt,
)

SEGMENTS = [Segment(0.0, 2.5, " Hello there. "), Segment(2.5, 3.0, "   "), Segment(3661.007, 3663.2, "Second part")]


def test_timestamps_never_overflow_the_millisecond_field():
    assert format_timestamp(59.9996) == "00:01:00,000"
    assert format_timestamp(3661.007) == "01:01:01,007"
    assert format_timestamp(3661.007, ".") == "01:01:01.007"
    assert format_timestamp(-3) == "00:00:00,000"
    assert format_timestamp(100 * 3600) == "100:00:00,000"
    assert format_clock(3725.9) == "1:02:05"


def test_srt_numbers_only_the_segments_with_words():
    assert render_srt(SEGMENTS) == (
        "1\n00:00:00,000 --> 00:00:02,500\nHello there.\n\n"
        "2\n01:01:01,007 --> 01:01:03,200\nSecond part\n"
    )


def test_vtt_has_a_header_and_dot_milliseconds():
    vtt = render_vtt(SEGMENTS)
    assert vtt.startswith("WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.500\n")


def test_the_lines_layout_puts_one_segment_on_each_line_with_optional_start_times():
    assert render_text(SEGMENTS, layout="lines") == "Hello there.\nSecond part\n"
    assert render_text(SEGMENTS, with_timestamps=True, layout="lines") == "[0:00:00] Hello there.\n[1:01:01] Second part\n"
    assert render_text([], layout="lines") == "" and plain_text(SEGMENTS) == "Hello there.\nSecond part"


def test_continuous_text_is_the_default_and_flows_without_line_breaks():
    assert render_text(SEGMENTS) == "Hello there. Second part\n"
    assert render(SEGMENTS, "txt") == "Hello there. Second part\n"
    assert render_text(SEGMENTS, with_timestamps=True) == "Hello there. Second part\n"      # times need the lines layout
    assert render_text([Segment(0, 1, "   ")]) == ""


def test_continuous_text_keeps_the_spacing_of_each_script():
    arabic = [Segment(0, 1, " مرحبا بكم"), Segment(1, 2, " في هذا الدرس.\n"), Segment(2, 3, "اليوم سنتعلم")]
    assert render_text(arabic) == "مرحبا بكم في هذا الدرس. اليوم سنتعلم\n"
    chinese = [Segment(0, 1, "你好，"), Segment(1, 2, "欢迎来到"), Segment(2, 3, "这节课。")]
    assert render_text(chinese) == "你好，欢迎来到这节课。\n"
    mixed = [Segment(0, 1, "Visit"), Segment(1, 2, "东京"), Segment(2, 3, "next year")]
    assert render_text(mixed) == "Visit东京next year\n"
    assert render_text([Segment(0, 1, "a\n\n b"), Segment(1, 2, "c")]) == "a b c\n"       # inner line breaks are folded away


def test_render_rejects_an_unknown_format():
    with pytest.raises(ValueError):
        render(SEGMENTS, "docx")


def test_output_goes_next_to_the_media_file_unless_a_folder_is_given(tmp_path):
    media = str(tmp_path / "lecture 1.mp4")
    assert output_path_for(media, None, "srt") == str(tmp_path / "lecture 1.srt")
    assert output_path_for(media, str(tmp_path / "out"), "txt") == str(tmp_path / "out" / "lecture 1.txt")


def test_a_failed_write_leaves_neither_a_partial_file_nor_a_damaged_old_one(tmp_path):
    target = tmp_path / "out.txt"
    target.write_text("good old content")
    write_atomically(str(target), "new")
    assert target.read_text() == "new" and not (tmp_path / "out.txt.part").exists()
    with pytest.raises(OSError):
        write_atomically(str(tmp_path / "missing-folder" / "out.txt"), "x")


def test_language_table_matches_what_faster_whisper_supports():
    tokenizer = pytest.importorskip("faster_whisper.tokenizer")
    assert set(WHISPER_LANGUAGES) == set(tokenizer._LANGUAGE_CODES)


def test_language_helpers():
    assert language_name("ar") == "Arabic" and language_name("xx") == "XX"
    names = [name for _code, name in languages_by_name()]
    assert names == sorted(names)


def test_media_extensions_cover_common_audio_and_video():
    assert {".mp3", ".wav", ".m4a", ".mp4", ".mkv", ".webm"} <= MEDIA_EXTENSIONS


def test_device_choice(monkeypatch):
    monkeypatch.setattr("core.media.hardware.gpu_available", lambda: True)
    assert resolve_device(DEVICE_AUTO) == GPU and resolve_device(DEVICE_CPU) == CPU
    monkeypatch.setattr("core.media.hardware.gpu_available", lambda: False)
    assert resolve_device(DEVICE_AUTO) == CPU and resolve_device(DEVICE_GPU) == GPU


def test_a_model_folder_is_checked_for_the_files_faster_whisper_needs(tmp_path):
    assert problems_with_model_dir("") and problems_with_model_dir(str(tmp_path / "nope"))
    assert len(problems_with_model_dir(str(tmp_path))) == 3
    for name in ("model.bin", "config.json", "vocabulary.json"):
        (tmp_path / name).write_text("x")
    assert problems_with_model_dir(str(tmp_path)) == []


def test_model_status_for_a_custom_folder(tmp_path):
    assert not model_status("custom", str(tmp_path)).ready
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (tmp_path / name).write_text("x")
    status = model_status("custom", str(tmp_path))
    assert status.ready and str(tmp_path) in status.message
