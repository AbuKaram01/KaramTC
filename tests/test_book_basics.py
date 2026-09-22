import os

from core.book import (
    IMAGE_MODES, BookProgress, book_paths, find_saved_job, native_text_looks_garbled,
    normalize_image_dpi, normalize_image_mode, normalize_jpeg_quality,
)
from core.book.constants import MAX_NAME_BYTES
from core.book.paths import sanitize_filename
from core.book.progress import progress_is_sane
from core.book.text_output import NoTextOutput, TextOutput, text_file_matches_progress
from config import BOOK_IMAGE_DPI, BOOK_IMAGE_DPI_RANGE


def test_normalizers_clamp_and_default():
    low, high = BOOK_IMAGE_DPI_RANGE
    assert normalize_image_dpi(10**6) == high
    assert normalize_image_dpi(-5) == low
    assert normalize_image_dpi("garbage") == BOOK_IMAGE_DPI
    assert normalize_image_dpi(None) == BOOK_IMAGE_DPI
    assert 1 <= normalize_jpeg_quality(0) <= 100


def test_image_mode_accepts_legacy_booleans():
    assert normalize_image_mode(True) == "on"
    assert normalize_image_mode(False) == "auto"
    assert normalize_image_mode("OFF") == "off"
    assert normalize_image_mode("nonsense") == "auto"
    assert all(normalize_image_mode(mode) == mode for mode in IMAGE_MODES)


def test_sanitize_filename_removes_path_characters():
    assert sanitize_filename('a/b\\c:d*e?') == "a_b_c_d_e_"
    assert sanitize_filename("...") == "book"


def test_long_arabic_names_stay_within_the_byte_limit_and_stay_distinct():
    first = sanitize_filename("كتاب" * 60 + "أ")
    second = sanitize_filename("كتاب" * 60 + "ب")
    assert len(first.encode()) <= MAX_NAME_BYTES
    assert first != second


def test_book_paths_never_overwrite_the_source_pdf(tmp_path):
    paths = book_paths(str(tmp_path / "novel.pdf"), None)
    assert paths.pdf_path.endswith("novel_searchable.pdf")
    assert paths.output_dir == str(tmp_path)
    assert os.path.basename(paths.progress_path).startswith(".")


def test_garbled_text_detection():
    assert native_text_looks_garbled("\ufffd" * 20 + "ok")
    assert not native_text_looks_garbled("Perfectly normal text, with a few symbols \u2022 \u2022")
    assert not native_text_looks_garbled("   \n ")


def test_progress_validation_rejects_damaged_records():
    good = {"status": "in_progress", "pdf_path": "/x.pdf", "completed_pages": 2, "page_types": ["text", "image"]}
    assert progress_is_sane(good)
    for damaged in (
        None, [], {"status": 1, "pdf_path": "/x"}, {**good, "completed_pages": -1}, {**good, "completed_pages": True},
        {**good, "page_types": ["text", "bogus"]}, {**good, "excluded_pages": ["a"]},
        {**good, "pdf_fingerprint": [1, 2, 3]}, {**good, "txt_size": -1}, {**good, "failed_pages": {"x": "y"}},
    ):
        assert not progress_is_sane(damaged)


def test_saved_job_is_found_and_detected_as_stale(tmp_path):
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF-1.4 original")
    paths = book_paths(str(pdf), None)
    progress = BookProgress(paths.progress_path)
    progress.data = {"status": "in_progress", "pdf_path": str(pdf), "pdf_fingerprint": [0, 0.0]}
    progress.save()

    job = find_saved_job(str(pdf), None)
    assert job is not None and job.progress.pdf_was_replaced(str(pdf))
    assert find_saved_job(str(tmp_path / "other.pdf"), None) is None


def test_saved_job_is_searched_next_to_the_pdf_when_asked(tmp_path):
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF")
    elsewhere = tmp_path / "out"
    elsewhere.mkdir()
    progress = BookProgress(book_paths(str(pdf), None).progress_path)
    progress.data = {"status": "in_progress", "pdf_path": str(pdf)}
    progress.save()

    assert find_saved_job(str(pdf), str(elsewhere)) is None
    job = find_saved_job(str(pdf), str(elsewhere), also_search_pdf_folder=True)
    assert job is not None and job.output_dir == str(tmp_path)


def test_text_output_resume_reconciliation(tmp_path):
    path = tmp_path / "out.txt"
    assert not text_file_matches_progress(str(path), 10)               # file is gone: restart
    path.write_bytes(b"x" * 25)
    assert text_file_matches_progress(str(path), 20) and path.stat().st_size == 20   # crash tail cut off
    assert not text_file_matches_progress(str(path), 30)               # shorter than recorded: restart
    assert text_file_matches_progress(str(path), None)


def test_text_output_writes_numbered_pages_and_supports_rollback(tmp_path):
    path = tmp_path / "out.txt"
    output = TextOutput(str(path), append=False)
    first = output.write_page(1, " hello ", with_page_marker=True)
    output.write_page(2, "world", with_page_marker=False)
    output.truncate_to(first)
    output.close()
    assert path.read_text() == "\n\n----- Page 1 -----\n\nhello\n"
    assert NoTextOutput().write_page(1, "x", True) is None
