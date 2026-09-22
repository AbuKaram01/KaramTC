import os
import threading

import pytest

from core.book import (
    BookJobSettings, BookProgress, BookRequest, CancelledError, book_paths, run_book_extraction,
)
from core.book.page_ocr import lighter_retry_dpi, page_failure_text
from providers.ocr_types import OcrPageError, OcrResult


def ok_ocr(image_path, lang, progress_cb=None, cancel_event=None, options=None):
    return OcrResult(text="OCR " + os.path.basename(image_path), confidence=80.0)


def request_for(pdf, tmp_path, provider="fake_ok", out_name="out", **settings):
    out = tmp_path / out_name
    out.mkdir(exist_ok=True)
    return BookRequest(pdf, provider, book_paths(pdf, str(out)), BookJobSettings(lang="eng", **settings))


def read_text(path):
    with open(path, encoding="utf-8") as text_file:
        return text_file.read()


def run(request, cancel_event, resume=False, events=None):
    callback = (lambda *args: events.append(args)) if events is not None else None
    return run_book_extraction(request, callback, cancel_event, resume=resume)


def test_native_and_scanned_pages_are_combined_in_order(make_pdf, register_provider, tmp_path, cancel_event):
    register_provider("fake_ok", ok_ocr)
    pdf = make_pdf(["text", "scan", "text"])
    result = run(request_for(pdf, tmp_path), cancel_event)

    text = read_text(result.txt_path)
    assert (result.total_pages, result.ocr_pages, result.pdf_path) == (3, 1, None)
    assert text.index("Page 1.") < text.index("OCR page_00002.jpg") < text.index("Page 3.")
    assert "----- Page 2 -----" in text
    assert result.avg_confidence == 80.0
    assert sorted(os.listdir(tmp_path / "out")) == ["book.txt"]       # progress file and page images cleaned up


def test_excluded_pages_are_left_out_but_keep_their_numbers(make_pdf, register_provider, tmp_path, cancel_event):
    register_provider("fake_ok", ok_ocr)
    pdf = make_pdf(["text", "text", "text"])
    result = run(request_for(pdf, tmp_path, excluded_pages={0}), cancel_event)
    text = read_text(result.txt_path)
    assert result.total_pages == 2
    assert "Page 1 -----" not in text and "Page 2 -----" in text and "Page 3 -----" in text


def test_searchable_pdf_is_assembled_for_pdf_output(make_pdf, register_provider, tmp_path, cancel_event):
    register_provider("fake_ok", ok_ocr)
    pdf = make_pdf(["text", "scan"])
    result = run(request_for(pdf, tmp_path, output_format="pdf"), cancel_event)
    import pymupdf
    assert result.txt_path is None
    with pymupdf.open(result.pdf_path) as document:
        assert document.page_count == 2


def test_native_only_mode_never_calls_ocr(make_pdf, register_provider, tmp_path, cancel_event):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("OCR must not run when image mode is off")
    register_provider("fake_ok", forbidden)
    pdf = make_pdf(["text", "scan"])
    result = run(request_for(pdf, tmp_path, image_mode="off"), cancel_event)
    assert result.ocr_pages == 0 and result.low_text_pages == 1


def test_a_scanned_book_in_native_only_mode_is_refused(make_pdf, tmp_path, cancel_event):
    pdf = make_pdf(["scan", "scan"])
    with pytest.raises(RuntimeError, match="scanned book"):
        run(request_for(pdf, tmp_path, image_mode="off"), cancel_event)
    assert not (tmp_path / "out" / ".book.ocr-progress.json").exists()


def test_excluding_every_page_is_an_error(make_pdf, tmp_path, cancel_event):
    pdf = make_pdf(["text"])
    with pytest.raises(RuntimeError, match="every page was excluded"):
        run(request_for(pdf, tmp_path, excluded_pages={0}), cancel_event)


def test_stop_then_resume_gives_the_same_text_as_an_uninterrupted_run(
    make_pdf, register_provider, tmp_path, cancel_event,
):
    pdf = make_pdf(["scan", "scan", "scan", "text"])
    register_provider("fake_ok", ok_ocr)
    reference = run(request_for(pdf, tmp_path, out_name="reference"), cancel_event)
    expected = read_text(reference.txt_path)

    calls = []

    def stop_after_first_page(image_path, lang, progress_cb=None, cancel_event=None, options=None):
        calls.append(image_path)
        interrupted.set()
        return ok_ocr(image_path, lang)

    interrupted = threading.Event()
    register_provider("fake_stop", stop_after_first_page)
    request = request_for(pdf, tmp_path, provider="fake_stop")
    with pytest.raises(CancelledError):
        run(request, interrupted)
    progress = BookProgress(request.paths.progress_path)
    assert progress.load() and progress.data["completed_pages"] == 1

    interrupted.clear()
    register_provider("fake_stop", ok_ocr)
    resumed = run(request, interrupted, resume=True)
    assert read_text(resumed.txt_path) == expected


def test_one_unreadable_page_is_skipped_with_a_placeholder(make_pdf, register_provider, tmp_path, cancel_event):
    def fail_on_second(image_path, lang, progress_cb=None, cancel_event=None, options=None):
        if "00002" in image_path:
            raise OcrPageError("page blew up")
        return ok_ocr(image_path, lang)
    register_provider("fake_ok", fail_on_second)
    pdf = make_pdf(["scan", "scan", "scan"])
    events = []
    result = run(request_for(pdf, tmp_path), cancel_event, events=events)

    text = read_text(result.txt_path)
    assert list(result.failed_pages) == [2] and "page blew up" in result.failed_pages[2]
    assert page_failure_text(2, result.failed_pages[2]) in text
    assert any(event[0] == "page_failed" and event[1] == 2 for event in events)


def test_five_failures_in_a_row_stop_the_job_and_can_be_resumed(
    make_pdf, register_provider, tmp_path, cancel_event,
):
    def always_fail(*_args, **_kwargs):
        raise OcrPageError("no language data")
    register_provider("fake_bad", always_fail)
    pdf = make_pdf(["scan"] * 6)
    request = request_for(pdf, tmp_path, provider="fake_bad")
    with pytest.raises(RuntimeError, match="5 pages in a row"):
        run(request, cancel_event)

    progress = BookProgress(request.paths.progress_path)
    assert progress.load() and progress.data["completed_pages"] == 0 and progress.data["failed_pages"] == {}
    assert os.path.getsize(request.paths.txt_path) == 0       # the failed pages' placeholders were rolled back

    register_provider("fake_bad", ok_ocr)
    result = run(request, cancel_event, resume=True)
    assert result.failed_pages == {} and result.ocr_pages == 6


def test_a_deleted_text_file_restarts_the_resume_from_page_one(make_pdf, register_provider, tmp_path, cancel_event):
    interrupted = threading.Event()

    def stop_early(image_path, lang, progress_cb=None, cancel_event=None, options=None):
        interrupted.set()
        return ok_ocr(image_path, lang)
    register_provider("fake_stop", stop_early)
    pdf = make_pdf(["scan", "scan"])
    request = request_for(pdf, tmp_path, provider="fake_stop")
    with pytest.raises(CancelledError):
        run(request, interrupted)
    os.remove(request.paths.txt_path)

    interrupted.clear()
    register_provider("fake_stop", ok_ocr)
    text = read_text(run(request, interrupted, resume=True).txt_path)
    assert "Page 1 -----" in text and "Page 2 -----" in text


def test_retry_resolution_is_lighter_but_never_below_the_floor():
    assert lighter_retry_dpi(300) == 150
    assert lighter_retry_dpi(200) == 120
    assert lighter_retry_dpi(100) is None
